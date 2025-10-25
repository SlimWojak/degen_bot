"""
Trade Kernel - Dry-run execution layer for simulated trading decisions.
Handles trade execution with safety filters and logging.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("trade_kernel")

class TradeSide(Enum):
    """Trade side enumeration."""
    BUY = "buy"
    SELL = "sell"

class TradeStatus(Enum):
    """Trade status enumeration."""
    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

@dataclass
class TradeDecision:
    """Structured trade decision."""
    symbol: str
    side: TradeSide
    size: float
    confidence: float
    reason: str
    timestamp: str
    status: TradeStatus = TradeStatus.PENDING
    execution_price: Optional[float] = None
    execution_time: Optional[str] = None

class TradeKernel:
    """Core trade execution kernel with safety filters."""
    
    def __init__(self):
        self.min_confidence = float(os.getenv("MIN_TRADE_CONFIDENCE", "0.65"))
        self.cooldown_seconds = int(os.getenv("TRADE_COOLDOWN_SECONDS", "60"))
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", "1000.0"))
        
        # Track last trade per symbol
        self.last_trade_time: Dict[str, datetime] = {}
        
        # Track positions (simulated)
        self.positions: Dict[str, float] = {}  # symbol -> size
        
        # Trade log path
        self.trade_log_path = f"data/positions-log-{datetime.now().strftime('%Y-%m-%d')}.json"
        
        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)
    
    async def execute(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a trade decision with safety checks.
        
        Args:
            decision: Trade decision from reasoning engine
            
        Returns:
            Execution result with status and details
        """
        try:
            # Create trade decision object
            trade = TradeDecision(
                symbol=decision.get("symbol", "BTC"),
                side=TradeSide(decision.get("side", "buy")),
                size=float(decision.get("size", 1.0)),
                confidence=float(decision.get("confidence", 0.5)),
                reason=decision.get("reason", "No reason provided"),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
            # Apply safety filters
            safety_check = await self._check_safety_filters(trade)
            if not safety_check["passed"]:
                trade.status = TradeStatus.REJECTED
                logger.warning(f"[trade_kernel] Trade rejected: {safety_check['reason']}")
                await self._log_trade(trade)
                return {
                    "status": "rejected",
                    "reason": safety_check["reason"],
                    "trade": trade.__dict__
                }
            
            # Execute the trade (simulated)
            execution_result = await self._execute_trade(trade)
            
            # Update position tracking
            self._update_position(trade)
            
            # Log the trade
            await self._log_trade(trade)
            
            logger.info(f"[trade_kernel] Trade executed: {trade.symbol} {trade.side.value} {trade.size} @ {trade.execution_price}")
            
            return {
                "status": "executed",
                "trade": trade.__dict__,
                "execution_result": execution_result
            }
            
        except Exception as e:
            logger.error(f"[trade_kernel] Execution failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "trade": decision
            }
    
    async def _check_safety_filters(self, trade: TradeDecision) -> Dict[str, Any]:
        """Check safety filters for trade execution."""
        # Check minimum confidence
        if trade.confidence < self.min_confidence:
            return {
                "passed": False,
                "reason": f"Confidence {trade.confidence:.2f} below minimum {self.min_confidence}"
            }
        
        # Check cooldown period
        if trade.symbol in self.last_trade_time:
            time_since_last = datetime.now(timezone.utc) - self.last_trade_time[trade.symbol]
            if time_since_last.total_seconds() < self.cooldown_seconds:
                return {
                    "passed": False,
                    "reason": f"Cooldown active: {self.cooldown_seconds - int(time_since_last.total_seconds())}s remaining"
                }
        
        # Check position size limits
        current_position = self.positions.get(trade.symbol, 0.0)
        new_position = current_position + (trade.size if trade.side == TradeSide.BUY else -trade.size)
        
        if abs(new_position) > self.max_position_size:
            return {
                "passed": False,
                "reason": f"Position size {abs(new_position):.2f} exceeds limit {self.max_position_size}"
            }
        
        return {"passed": True, "reason": "All safety checks passed"}
    
    async def _execute_trade(self, trade: TradeDecision) -> Dict[str, Any]:
        """Execute the trade (simulated for now)."""
        # Simulate execution price (mock market data)
        base_price = 50000.0  # Mock BTC price
        spread = 0.001  # 0.1% spread
        
        if trade.side == TradeSide.BUY:
            execution_price = base_price * (1 + spread)
        else:
            execution_price = base_price * (1 - spread)
        
        # Update trade with execution details
        trade.execution_price = execution_price
        trade.execution_time = datetime.now(timezone.utc).isoformat()
        trade.status = TradeStatus.EXECUTED
        
        # Update last trade time
        self.last_trade_time[trade.symbol] = datetime.now(timezone.utc)
        
        return {
            "execution_price": execution_price,
            "execution_time": trade.execution_time,
            "slippage": spread,
            "status": "executed"
        }
    
    def _update_position(self, trade: TradeDecision) -> None:
        """Update position tracking."""
        current_position = self.positions.get(trade.symbol, 0.0)
        
        if trade.side == TradeSide.BUY:
            new_position = current_position + trade.size
        else:
            new_position = current_position - trade.size
        
        self.positions[trade.symbol] = new_position
        
        logger.info(f"[trade_kernel] Position updated: {trade.symbol} = {new_position:.2f}")
    
    async def _log_trade(self, trade: TradeDecision) -> None:
        """Log trade to daily file."""
        try:
            log_entry = {
                "timestamp": trade.timestamp,
                "symbol": trade.symbol,
                "side": trade.side.value,
                "size": trade.size,
                "confidence": trade.confidence,
                "reason": trade.reason,
                "status": trade.status.value,
                "execution_price": trade.execution_price,
                "execution_time": trade.execution_time
            }
            
            # Append to daily log file
            with open(self.trade_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            logger.error(f"[trade_kernel] Failed to log trade: {e}")
    
    def get_positions(self) -> Dict[str, float]:
        """Get current positions."""
        return self.positions.copy()
    
    def get_last_trade_time(self, symbol: str) -> Optional[datetime]:
        """Get last trade time for a symbol."""
        return self.last_trade_time.get(symbol)
    
    def get_cooldown_remaining(self, symbol: str) -> int:
        """Get remaining cooldown seconds for a symbol."""
        if symbol not in self.last_trade_time:
            return 0
        
        time_since_last = datetime.now(timezone.utc) - self.last_trade_time[symbol]
        remaining = self.cooldown_seconds - int(time_since_last.total_seconds())
        return max(0, remaining)
    
    def get_trade_history(self, symbol: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get trade history from log file."""
        try:
            if not os.path.exists(self.trade_log_path):
                return []
            
            history = []
            with open(self.trade_log_path, "r") as f:
                for line in f:
                    if line.strip():
                        trade = json.loads(line)
                        if symbol is None or trade.get("symbol") == symbol:
                            history.append(trade)
            
            return history[-limit:] if history else []
            
        except Exception as e:
            logger.error(f"[trade_kernel] Failed to get trade history: {e}")
            return []

# Global trade kernel instance
trade_kernel = TradeKernel()
