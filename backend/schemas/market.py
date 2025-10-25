"""
Market data schemas using Pydantic for validation and serialization.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class BookLevel(BaseModel):
    """Single level in order book."""
    px: float  # Price
    sz: float  # Size

class BookSide(BaseModel):
    """One side of order book (bids or asks)."""
    levels: List[BookLevel]  # Depth N levels

class Microstructure(BaseModel):
    """Microstructure features computed from order book."""
    ts: int                     # ms epoch
    mid: float                  # Mid price
    spread_bps: float           # Spread in basis points
    depth_bid_usd: float       # Total bid depth in USD
    depth_ask_usd: float       # Total ask depth in USD
    obi: float                  # Order book imbalance: (bidVol - askVol) / (bidVol + askVol)
    ofi: float                  # Order flow imbalance (approximate)
    microprice: float          # Microprice: (ask*bidSz + bid*askSz) / (bidSz + askSz)
    impact_usd: Dict[str, float]  # Price impact for different notional sizes
    rtn_5s: Optional[float] = None   # 5-second return
    rtn_30s: Optional[float] = None  # 30-second return

class Snapshot(BaseModel):
    """Complete market snapshot for a symbol."""
    symbol: str
    book_ts: int               # Book timestamp in ms
    bids: BookSide
    asks: BookSide
    micro: Microstructure

class ContextV1(BaseModel):
    """Agent context v1 - market data + account + limits."""
    symbols: List[str]
    market: Dict[str, Microstructure]  # symbol -> micro features
    account: Dict[str, Any]           # Account overview from state_service
    limits: Dict[str, Any]            # Trading limits and caps
    meta: Dict[str, Any] = Field(default_factory=dict)

class MarketHealth(BaseModel):
    """Market WebSocket health status."""
    ws: str                    # "connected" | "reconnecting" | "down"
    lag_ms: int               # Lag in milliseconds
    symbols_connected: List[str]  # Symbols with active feeds
    last_update_ts: int        # Last update timestamp
    error_count: int          # Error count since start
