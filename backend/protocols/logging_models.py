"""
Logging Models - Phase ε.1 Purification Pass
TypedDict models for structured logging to replace untyped dicts.
"""

from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime


class DecisionLog(TypedDict):
    """Structured log for AI decisions."""
    timestamp: str
    intent_id: str
    symbol: str
    side: str
    size: float
    confidence: float
    rationale: str
    action: str  # "buy", "sell", "hold"
    mode: str  # "sim", "live"
    dry_run: bool
    guards: Dict[str, Any]
    market_data: Dict[str, Any]
    position_data: Dict[str, Any]


class OrderAuditRow(TypedDict):
    """Structured audit log for order events."""
    timestamp: str
    event: str  # "order_submitted", "order_filled", "order_cancelled"
    intent_id: str
    order_id: Optional[str]
    symbol: str
    side: str
    size: float
    price: Optional[float]
    status: str
    mode: str  # "sim", "live"
    dry_run: bool
    error: Optional[str]
    metadata: Dict[str, Any]


class MarketTick(TypedDict):
    """Structured market tick data."""
    timestamp: int
    symbol: str
    price: float
    size: float
    side: str  # "buy", "sell"
    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]


class HealthMetrics(TypedDict):
    """Structured health metrics."""
    timestamp: str
    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    metrics: Dict[str, Any]
    errors: List[str]
    warnings: List[str]
