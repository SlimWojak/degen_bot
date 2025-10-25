"""
Lucidity schemas for human-readable state information.
Provides comprehensive view of system state for monitoring and debugging.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

class AccountInfo(BaseModel):
    """Account information for Lucidity feed."""
    equity: float
    margin_ratio: float
    collateral_health: str  # "healthy", "warning", "critical"
    liquidation_buffer: float
    free_collateral: float
    total_value: float
    maintenance_margin: float

class PositionInfo(BaseModel):
    """Position information for Lucidity feed."""
    symbol: str
    size: float
    avg_px: float
    upnl: float
    delta: float  # vs target = 0
    leverage_est: float
    side: str  # "long" or "short"
    notional: float
    margin_used: float

class MarketInfo(BaseModel):
    """Market information for Lucidity feed."""
    mid: Optional[float]
    spread_bps: Optional[float]
    obi: Optional[float]  # Order book imbalance
    rtn_5s: Optional[float]  # 5-second return
    funding_rate: Optional[float]
    open_interest: Optional[float]
    last_update_ms: int

class RiskInfo(BaseModel):
    """Risk management information."""
    max_notional_usd: float
    cross_bps_cap: float
    trading_enabled: bool
    kill_switch: bool
    position_risk_pct: float
    daily_dd_limit: float
    budget_drawdown_pct: float
    budget_guard_triggered: bool

class DataHealthInfo(BaseModel):
    """Data health information."""
    status: str
    mids_nonnull_pct: Dict[str, float]
    avg_last_msg_ms_ago: Dict[str, int]

class AIHealthInfo(BaseModel):
    """AI health information."""
    parse_success_1h: float
    reprompt_rate: float
    mode: str

class LiveGuardInfo(BaseModel):
    """Live guard information."""
    active: bool
    mode: str
    reason: str

class WSHealthInfo(BaseModel):
    """WebSocket health information."""
    connected: bool
    last_tick_s_ago: float
    symbols_active: int
    reconnects: int
    total_ticks: int
    error_count: int

class OpsInfo(BaseModel):
    """Operations and rate limiting information."""
    info_limiter: Dict[str, Any]
    order_limiter: Dict[str, Any]
    ws_connected: bool
    last_msg_ms_ago: Optional[int]
    reconnects: int
    backoff_ms: Optional[int] = None
    lag_ms: int
    stale: bool = False
    stale_fields: List[str] = []
    data_health: Optional[DataHealthInfo] = None
    ai_health: Optional[AIHealthInfo] = None
    live_guard: Optional[LiveGuardInfo] = None
    ws_health: Optional[WSHealthInfo] = None

class SimulationInfo(BaseModel):
    """Simulation metrics and performance."""
    trades: int
    win_rate: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    avg_slippage_bps: float

class ReflectionInfo(BaseModel):
    """Reflection and scoring information."""
    win_rate: float
    pnl_10_usd: float
    policy_score: float
    updated_at: Optional[str] = None

class LucidityFeed(BaseModel):
    """Complete Lucidity feed for human-readable state."""
    account: AccountInfo
    positions: List[PositionInfo]
    market: Dict[str, MarketInfo]
    risk: RiskInfo
    ops: OpsInfo
    meta: Dict[str, Any]
    simulation: Optional[SimulationInfo] = None
    reflection: Optional[ReflectionInfo] = None

class ContextV2(BaseModel):
    """Enhanced agent context with Lucidity feed."""
    symbols: List[str]
    market: Dict[str, Any]
    account: Dict[str, Any]
    limits: Dict[str, Any]
    lucidity: LucidityFeed
    meta: Dict[str, Any]
