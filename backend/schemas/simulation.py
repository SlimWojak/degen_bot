"""
Simulation schemas for DeepSeek decision validation and structured logging.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, validator

class DeepSeekDecision(BaseModel):
    """DeepSeek decision output schema."""
    action: Literal["BUY", "SELL", "HOLD"]
    symbol: Literal["BTC", "ETH", "SOL", "DOGE", "XRP", "HYPE"]
    notional_usd: float = Field(ge=1.0, le=1000.0, description="Notional amount in USD")
    reason: str = Field(min_length=5, max_length=200, description="Short explanation for the decision")
    
    @validator('notional_usd')
    def validate_notional(cls, v):
        if v <= 0:
            raise ValueError('Notional must be positive')
        return v
    
    @validator('reason')
    def validate_reason(cls, v):
        if not v.strip():
            raise ValueError('Reason cannot be empty')
        return v.strip()

class DecisionLog(BaseModel):
    """Structured decision log entry."""
    ts: str  # ISO timestamp
    symbol: str
    action: str
    notional: float
    fill_px: Optional[float] = None
    result: str  # "filled", "rejected", "error"
    reason: str
    pnl_after: Optional[float] = None
    intent_id: str
    latency_ms: Optional[float] = None

class SimulationMetrics(BaseModel):
    """Simulation performance metrics."""
    trades: int
    win_rate: float
    realized_pnl_usd: float
    unrealized_pnl_usd: float
    avg_slippage_bps: float

class EvaluationSummary(BaseModel):
    """Evaluation summary for DeepSeek reflection."""
    period: str  # "last_10_trades", "daily", etc.
    trades: int
    wins: int
    win_rate_pct: float
    pnl_total_usd: float
    avg_slippage_bps: float
    summary_text: str  # Human-readable summary
