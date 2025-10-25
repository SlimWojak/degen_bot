"""
Market Feed Protocol - Phase ε.1 Purification Pass
Defines the interface for market data access.
"""

from typing import Protocol, Optional, Dict, Any
from abc import abstractmethod


class MarketFeed(Protocol):
    """Protocol for market data feed access."""
    
    @abstractmethod
    def get_cached(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached market data for symbol."""
        ...
    
    @abstractmethod
    def last_tick_s_ago(self, symbol: str) -> float:
        """Get seconds since last tick for symbol."""
        ...
    
    @abstractmethod
    def get_reconnect_count(self) -> int:
        """Get total reconnection count."""
        ...
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if feed is connected."""
        ...
