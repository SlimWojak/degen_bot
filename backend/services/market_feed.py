"""
Market feed protocol interface for unified market data access.
"""

from typing import Protocol, Optional, Dict, Any

class MarketFeed(Protocol):
    """Protocol for market data feed implementations."""
    
    async def start(self) -> None:
        """Start the market feed."""
        ...
    
    async def stop(self) -> None:
        """Stop the market feed."""
        ...
    
    def get_cached(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached market data for symbol (non-blocking)."""
        ...
    
    def last_tick_s_ago(self) -> float:
        """Get seconds since last tick."""
        ...
    
    def reconnect_count(self) -> int:
        """Get total reconnection count."""
        ...
    
    def is_connected(self) -> bool:
        """Check if feed is connected."""
        ...
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get health metrics."""
        ...
