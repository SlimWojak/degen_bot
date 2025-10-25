"""
Budget guard for daily loss limits.
Tracks realized PnL and simulated PnL per 24h rolling window.
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)

@dataclass
class PnLRecord:
    """Record of PnL with timestamp."""
    timestamp: float
    realized_pnl: float
    simulated_pnl: float
    total_pnl: float

class BudgetGuard:
    """Tracks daily PnL and enforces budget limits."""
    
    def __init__(self, max_drawdown_pct: float = 10.0, window_hours: int = 24):
        self.max_drawdown_pct = max_drawdown_pct
        self.window_seconds = window_hours * 3600
        self.records = deque()  # PnL records
        self.initial_balance = 10000.0  # Default starting balance
        self.triggered = False
        self.triggered_at: Optional[float] = None
    
    def set_initial_balance(self, balance: float):
        """Set the initial balance for drawdown calculation."""
        self.initial_balance = balance
        logger.info(f"Budget guard initial balance set to: {balance}")
    
    def record_pnl(self, realized_pnl: float = 0.0, simulated_pnl: float = 0.0):
        """Record PnL for the current period."""
        now = time.time()
        total_pnl = realized_pnl + simulated_pnl
        
        record = PnLRecord(now, realized_pnl, simulated_pnl, total_pnl)
        self.records.append(record)
        
        # Clean old records outside window
        cutoff = now - self.window_seconds
        while self.records and self.records[0].timestamp < cutoff:
            self.records.popleft()
        
        # Check if budget limit exceeded
        self._check_budget_limit()
        
        logger.debug(f"Recorded PnL: realized={realized_pnl}, simulated={simulated_pnl}, total={total_pnl}")
    
    def _check_budget_limit(self):
        """Check if budget limit has been exceeded."""
        if not self.records:
            return
        
        # Calculate total PnL over window
        total_pnl = sum(record.total_pnl for record in self.records)
        drawdown_pct = abs(total_pnl) / self.initial_balance * 100
        
        if drawdown_pct >= self.max_drawdown_pct and not self.triggered:
            self.triggered = True
            self.triggered_at = time.time()
            logger.warning(f"BUDGET_GUARD_TRIGGERED: drawdown={drawdown_pct:.2f}% >= {self.max_drawdown_pct}%")
        elif drawdown_pct < self.max_drawdown_pct and self.triggered:
            # Reset if we're back under the limit
            self.triggered = False
            self.triggered_at = None
            logger.info(f"BUDGET_GUARD_RESET: drawdown={drawdown_pct:.2f}% < {self.max_drawdown_pct}%")
    
    def is_triggered(self) -> bool:
        """Check if budget guard is currently triggered."""
        return self.triggered
    
    def get_status(self) -> Dict:
        """Get budget guard status."""
        if not self.records:
            return {
                "triggered": False,
                "drawdown_pct": 0.0,
                "total_pnl": 0.0,
                "initial_balance": self.initial_balance,
                "max_drawdown_pct": self.max_drawdown_pct
            }
        
        total_pnl = sum(record.total_pnl for record in self.records)
        drawdown_pct = abs(total_pnl) / self.initial_balance * 100
        
        return {
            "triggered": self.triggered,
            "drawdown_pct": drawdown_pct,
            "total_pnl": total_pnl,
            "initial_balance": self.initial_balance,
            "max_drawdown_pct": self.max_drawdown_pct,
            "triggered_at": self.triggered_at,
            "records_count": len(self.records)
        }
    
    def reset(self):
        """Reset budget guard (for testing)."""
        self.records.clear()
        self.triggered = False
        self.triggered_at = None
        logger.info("Budget guard reset")

# Global budget guard instance
_budget_guard = BudgetGuard()

def record_pnl(realized_pnl: float = 0.0, simulated_pnl: float = 0.0):
    """Record PnL for budget tracking."""
    _budget_guard.record_pnl(realized_pnl, simulated_pnl)

def is_triggered() -> bool:
    """Check if budget guard is triggered."""
    return _budget_guard.is_triggered()

def get_status() -> Dict:
    """Get budget guard status."""
    return _budget_guard.get_status()

def set_initial_balance(balance: float):
    """Set initial balance for drawdown calculation."""
    _budget_guard.set_initial_balance(balance)

def reset():
    """Reset budget guard (for testing)."""
    _budget_guard.reset()
