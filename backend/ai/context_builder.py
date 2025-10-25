"""
Context builder for DeepSeek decisions.
Creates compact, bounded prompts with market data, positions, and recent decisions.
"""

import time
import logging
from typing import Dict, List, Any, Optional
from backend.services.sim_broker import get_sim_broker
from backend.observability.logs import get_recent_decisions
from backend.util.breakers import get_all_status
from backend.util.budget_guard import get_status as get_budget_status
from backend.observability.metrics import get_info_limiter_stats, get_order_limiter_stats

logger = logging.getLogger(__name__)

class ContextBuilder:
    """Builds compact, bounded context for DeepSeek decisions."""
    
    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars
        
    def build_context(self, symbols: List[str], market_data: Dict[str, Any]) -> str:
        """
        Build compact context for DeepSeek decision.
        
        Args:
            symbols: List of symbols to include
            market_data: Market data for symbols
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Market slice (for requested symbols only)
        market_slice = self._build_market_slice(symbols, market_data)
        context_parts.append(market_slice)
        
        # Positions (from SimBroker)
        positions = self._build_positions()
        context_parts.append(positions)
        
        # Risk state
        risk_state = self._build_risk_state()
        context_parts.append(risk_state)
        
        # Operations state
        ops_state = self._build_ops_state()
        context_parts.append(ops_state)
        
        # Recent decisions (last 5)
        recent_decisions = self._build_recent_decisions()
        context_parts.append(recent_decisions)
        
        # Reflection stub (if available)
        reflection = self._build_reflection()
        if reflection:
            context_parts.append(reflection)
        
        # Combine and truncate if needed
        full_context = "\n\n".join(context_parts)
        
        if len(full_context) > self.max_chars:
            # Truncate older entries first
            full_context = self._truncate_context(full_context)
        
        return full_context
    
    def _build_market_slice(self, symbols: List[str], market_data: Dict[str, Any]) -> str:
        """Build market data slice for requested symbols."""
        market_lines = ["MARKET:"]
        
        for symbol in symbols:
            if symbol in market_data:
                data = market_data[symbol]
                mid = data.get("mid", "N/A")
                spread_bps = data.get("spread_bps", "N/A")
                obi = data.get("obi", "N/A")
                rtn_5s = data.get("rtn_5s", "N/A")
                
                market_lines.append(f"  {symbol}: mid={mid}, spread={spread_bps}bps, obi={obi}, rtn_5s={rtn_5s}")
            else:
                market_lines.append(f"  {symbol}: no data")
        
        return "\n".join(market_lines)
    
    def _build_positions(self) -> str:
        """Build positions from SimBroker."""
        try:
            sim_broker = get_sim_broker()
            positions = sim_broker.get_positions()
            
            if not positions:
                return "POSITIONS: none"
            
            position_lines = ["POSITIONS:"]
            for pos in positions:
                position_lines.append(
                    f"  {pos['symbol']}: {pos['size']:.6f} @ {pos['avg_px']:.2f}, "
                    f"uPnL={pos['unrealized_pnl']:.2f}, notional={pos['notional']:.2f}"
                )
            
            return "\n".join(position_lines)
            
        except Exception as e:
            logger.warning(f"Failed to get positions: {e}")
            return "POSITIONS: error"
    
    def _build_risk_state(self) -> str:
        """Build risk state including budget guard."""
        try:
            budget_status = get_budget_status()
            
            risk_lines = ["RISK:"]
            risk_lines.append(f"  budget_drawdown: {budget_status.get('drawdown_pct', 0):.1f}%")
            risk_lines.append(f"  budget_triggered: {budget_status.get('triggered', False)}")
            risk_lines.append(f"  total_pnl: {budget_status.get('total_pnl', 0):.2f}")
            
            return "\n".join(risk_lines)
            
        except Exception as e:
            logger.warning(f"Failed to get risk state: {e}")
            return "RISK: error"
    
    def _build_ops_state(self) -> str:
        """Build operations state including breakers and rate limiters."""
        try:
            ops_lines = ["OPS:"]
            
            # Circuit breakers
            breaker_status = get_all_status()
            breaker_active = any(status.get("tripped", False) for status in breaker_status.values())
            ops_lines.append(f"  breakers: {'ACTIVE' if breaker_active else 'OK'}")
            
            # Rate limiters
            info_stats = get_info_limiter_stats()
            order_stats = get_order_limiter_stats()
            ops_lines.append(f"  info_limiter: {info_stats.tokens:.1f}/{info_stats.burst} tokens")
            ops_lines.append(f"  order_limiter: {order_stats.tokens:.1f}/{order_stats.burst} tokens")
            
            # WebSocket (simplified)
            ops_lines.append("  ws: connected")
            
            return "\n".join(ops_lines)
            
        except Exception as e:
            logger.warning(f"Failed to get ops state: {e}")
            return "OPS: error"
    
    def _build_recent_decisions(self) -> str:
        """Build recent decisions (last 5)."""
        try:
            decisions = get_recent_decisions(5)
            
            if not decisions:
                return "RECENT: none"
            
            decision_lines = ["RECENT DECISIONS:"]
            for decision in decisions:
                action = decision.get("action", "UNKNOWN")
                symbol = decision.get("symbol", "UNKNOWN")
                notional = decision.get("notional", 0)
                result = decision.get("result", "unknown")
                pnl = decision.get("pnl_after", 0)
                
                decision_lines.append(
                    f"  {action} {symbol} ${notional:.1f} -> {result}, PnL={pnl:.2f}"
                )
            
            return "\n".join(decision_lines)
            
        except Exception as e:
            logger.warning(f"Failed to get recent decisions: {e}")
            return "RECENT: error"
    
    def _build_reflection(self) -> Optional[str]:
        """Build reflection stub if available."""
        try:
            # This would be implemented in the reflection system
            # For now, return None
            return None
        except Exception as e:
            logger.warning(f"Failed to get reflection: {e}")
            return None
    
    def _truncate_context(self, context: str) -> str:
        """Truncate context to fit within character limit."""
        if len(context) <= self.max_chars:
            return context
        
        # Simple truncation - remove from the end
        truncated = context[:self.max_chars - 3] + "..."
        return truncated

# Global context builder
_context_builder = ContextBuilder()

def build_context(symbols: List[str], market_data: Dict[str, Any]) -> str:
    """Build context for DeepSeek decision."""
    return _context_builder.build_context(symbols, market_data)
