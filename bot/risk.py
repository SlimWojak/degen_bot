# bot/risk.py
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class RiskLimits:
    max_leverage: float
    position_risk: float     # % of equity per trade (e.g., 0.02)
    daily_dd_limit: float    # daily max drawdown (e.g., 0.10)

class RiskGovernor:
    def __init__(self, limits: RiskLimits, get_equity, get_open_notional):
        self.l = limits
        self.get_equity = get_equity
        self.get_open_notional = get_open_notional

    def per_trade_notional_cap(self) -> float:
        return self.get_equity() * self.l.position_risk

    def allow_order(self, symbol: str, intended_notional: float, leverage: float) -> tuple[bool, str]:
        """
        Check if an order is allowed based on risk limits.
        
        Args:
            symbol: Trading symbol
            intended_notional: Intended notional value of the trade
            leverage: Leverage for the trade
            
        Returns:
            tuple[bool, str]: (allowed, reason)
        """
        if leverage > self.l.max_leverage:
            logger.warning(f"[RISK] Blocked {symbol}: leverage {leverage} exceeds max {self.l.max_leverage}")
            return False, "leverage_exceeds_max"
            
        if intended_notional > self.per_trade_notional_cap():
            cap = self.per_trade_notional_cap()
            logger.warning(f"[RISK] Blocked {symbol}: notional {intended_notional} exceeds per-trade cap {cap}")
            return False, "notional_exceeds_per_trade_cap"
            
        current_exposure = self.get_open_notional()
        total_exposure = current_exposure + intended_notional
        max_total_exposure = self.get_equity() * 0.5  # 50% max portfolio exposure
        
        if total_exposure > max_total_exposure:
            logger.warning(f"[RISK] Blocked {symbol}: total exposure {total_exposure} exceeds 50% of equity {max_total_exposure}")
            return False, "portfolio_exposure_too_high"
            
        # daily drawdown check lives in your PnL loop; skip here
        logger.info(f"[RISK] Allowed {symbol}: notional={intended_notional}, leverage={leverage}")
        return True, "ok"