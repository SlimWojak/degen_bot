"""
SimBroker - Simulated trading execution engine.
Mimics Hyperliquid fills with configurable slippage and fees.
"""

import time
import json
import random
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import os

logger = logging.getLogger(__name__)

@dataclass
class SimPosition:
    """Simulated position."""
    symbol: str
    size: float  # Positive for long, negative for short
    avg_px: float
    unrealized_pnl: float
    realized_pnl: float
    notional: float
    timestamp: float

@dataclass
class SimTrade:
    """Simulated trade fill."""
    symbol: str
    side: str  # "BUY" or "SELL"
    size: float
    fill_px: float
    notional: float
    fee: float
    slippage_bps: float
    timestamp: float
    intent_id: str

@dataclass
class SimBalance:
    """Simulated account balance."""
    cash_usd: float
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    total_notional: float
    timestamp: float

class SimBroker:
    """Simulated trading broker with fill logic and PnL tracking."""
    
    def __init__(self, initial_cash: float = 10000.0, fee_rate: float = 0.0002):
        self.initial_cash = initial_cash
        self.fee_rate = fee_rate  # 0.02% default
        self.positions: Dict[str, SimPosition] = {}
        self.trades: List[SimTrade] = []
        self.balance = SimBalance(
            cash_usd=initial_cash,
            total_pnl=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            total_notional=0.0,
            timestamp=time.time()
        )
        self.session_id = datetime.now().strftime("%Y-%m-%d")
        self.log_dir = "data/simlog"
        os.makedirs(self.log_dir, exist_ok=True)
    
    def get_mid_price(self, symbol: str) -> Optional[float]:
        """Get current mid price for symbol (from market data)."""
        # In real implementation, this would get from market_ws
        # For now, return mock prices
        mock_prices = {
            "BTC": 65000.0,
            "ETH": 3000.0,
            "SOL": 150.0
        }
        return mock_prices.get(symbol)
    
    def calculate_slippage(self, symbol: str, size: float, side: str) -> float:
        """Calculate slippage in basis points."""
        # Base slippage + size impact
        base_slippage = random.uniform(1, 5)  # 1-5 bps base
        size_impact = min(abs(size) * 0.1, 10)  # Up to 10 bps for large orders
        return base_slippage + size_impact
    
    def execute_order(self, symbol: str, side: str, notional_usd: float, intent_id: str) -> Optional[SimTrade]:
        """Execute a simulated order."""
        mid_price = self.get_mid_price(symbol)
        if not mid_price:
            logger.warning(f"No mid price available for {symbol}")
            return None
        
        # Calculate size and fill price
        size = notional_usd / mid_price
        if side == "SELL":
            size = -size
        
        # Calculate slippage
        slippage_bps = self.calculate_slippage(symbol, size, side)
        slippage_pct = slippage_bps / 10000.0
        
        # Apply slippage to fill price
        if side == "BUY":
            fill_px = mid_price * (1 + slippage_pct)
        else:
            fill_px = mid_price * (1 - slippage_pct)
        
        # Calculate fee
        notional = abs(size) * fill_px
        fee = notional * self.fee_rate
        
        # Create trade record
        trade = SimTrade(
            symbol=symbol,
            side=side,
            size=size,
            fill_px=fill_px,
            notional=notional,
            fee=fee,
            slippage_bps=slippage_bps,
            timestamp=time.time(),
            intent_id=intent_id
        )
        
        # Update position
        self._update_position(symbol, size, fill_px, fee)
        
        # Add to trades list
        self.trades.append(trade)
        
        # Persist to file
        self._persist_trade(trade)
        
        logger.info(f"SimBroker executed {side} {size:.4f} {symbol} @ {fill_px:.2f} (slip: {slippage_bps:.1f}bps)")
        
        return trade
    
    def _update_position(self, symbol: str, size: float, fill_px: float, fee: float):
        """Update position after trade."""
        if symbol not in self.positions:
            self.positions[symbol] = SimPosition(
                symbol=symbol,
                size=0.0,
                avg_px=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                notional=0.0,
                timestamp=time.time()
            )
        
        pos = self.positions[symbol]
        
        # Update position size and average price
        if (pos.size > 0 and size > 0) or (pos.size < 0 and size < 0):
            # Same direction - update average price
            total_notional = pos.size * pos.avg_px + size * fill_px
            pos.size += size
            pos.avg_px = total_notional / pos.size if pos.size != 0 else 0.0
        else:
            # Opposite direction or new position
            if abs(size) >= abs(pos.size):
                # Closing or reversing position
                if pos.size != 0:
                    # Realize PnL on closed portion
                    closed_pnl = pos.size * (fill_px - pos.avg_px)
                    pos.realized_pnl += closed_pnl
                    self.balance.realized_pnl += closed_pnl
                
                # Set new position
                pos.size = size
                pos.avg_px = fill_px
            else:
                # Partial close
                closed_pnl = -size * (fill_px - pos.avg_px)
                pos.realized_pnl += closed_pnl
                self.balance.realized_pnl += closed_pnl
                pos.size += size
        
        # Update notional
        pos.notional = abs(pos.size) * pos.avg_px
        
        # Update balance
        self.balance.cash_usd -= fee
        self.balance.total_notional = sum(p.notional for p in self.positions.values())
        
        # Update timestamps
        pos.timestamp = time.time()
        self.balance.timestamp = time.time()
    
    def _persist_trade(self, trade: SimTrade):
        """Persist trade to daily log file."""
        log_file = os.path.join(self.log_dir, f"{self.session_id}.jsonl")
        with open(log_file, "a") as f:
            f.write(json.dumps(asdict(trade), default=str) + "\n")
    
    def get_positions(self) -> List[Dict]:
        """Get current positions."""
        # Update unrealized PnL
        self._update_unrealized_pnl()
        
        return [
            {
                "symbol": pos.symbol,
                "size": pos.size,
                "avg_px": pos.avg_px,
                "unrealized_pnl": pos.unrealized_pnl,
                "realized_pnl": pos.realized_pnl,
                "notional": pos.notional,
                "timestamp": pos.timestamp
            }
            for pos in self.positions.values()
            if pos.size != 0
        ]
    
    def get_trades(self, limit: int = 50) -> List[Dict]:
        """Get recent trades."""
        return [
            {
                "symbol": trade.symbol,
                "side": trade.side,
                "size": trade.size,
                "fill_px": trade.fill_px,
                "notional": trade.notional,
                "fee": trade.fee,
                "slippage_bps": trade.slippage_bps,
                "timestamp": trade.timestamp,
                "intent_id": trade.intent_id
            }
            for trade in self.trades[-limit:]
        ]
    
    def get_balance(self) -> Dict:
        """Get current balance."""
        self._update_unrealized_pnl()
        return {
            "cash_usd": self.balance.cash_usd,
            "total_pnl": self.balance.total_pnl,
            "realized_pnl": self.balance.realized_pnl,
            "unrealized_pnl": self.balance.unrealized_pnl,
            "total_notional": self.balance.total_notional,
            "timestamp": self.balance.timestamp
        }
    
    def _update_unrealized_pnl(self):
        """Update unrealized PnL for all positions."""
        total_unrealized = 0.0
        
        for pos in self.positions.values():
            if pos.size != 0:
                current_price = self.get_mid_price(pos.symbol)
                if current_price:
                    pos.unrealized_pnl = pos.size * (current_price - pos.avg_px)
                    total_unrealized += pos.unrealized_pnl
        
        self.balance.unrealized_pnl = total_unrealized
        self.balance.total_pnl = self.balance.realized_pnl + self.balance.unrealized_pnl
    
    def get_metrics(self) -> Dict:
        """Get simulation metrics."""
        if not self.trades:
            return {
                "trades": 0,
                "win_rate": 0.0,
                "realized_pnl_usd": 0.0,
                "unrealized_pnl_usd": 0.0,
                "avg_slippage_bps": 0.0
            }
        
        # Calculate win rate from realized PnL
        winning_trades = sum(1 for trade in self.trades if trade.side == "BUY" and trade.size > 0)
        total_trades = len(self.trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Calculate average slippage
        avg_slippage = sum(trade.slippage_bps for trade in self.trades) / len(self.trades)
        
        return {
            "trades": total_trades,
            "win_rate": win_rate,
            "realized_pnl_usd": self.balance.realized_pnl,
            "unrealized_pnl_usd": self.balance.unrealized_pnl,
            "avg_slippage_bps": avg_slippage
        }

# Global SimBroker instance
_sim_broker = SimBroker()

def get_sim_broker() -> SimBroker:
    """Get the global SimBroker instance."""
    return _sim_broker
