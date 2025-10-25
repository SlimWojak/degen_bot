"""
Market data cache with non-blocking access.
Provides tick→cache bridge for real-time market data.
"""

import time
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from threading import RLock

logger = logging.getLogger(__name__)

@dataclass
class CachedTick:
    """Cached tick data."""
    mid: Optional[float]
    spread_bps: Optional[float]
    obi: Optional[float]
    last_tick_ts: float
    symbol: str

class MarketCache:
    """Thread-safe market data cache with non-blocking access."""
    
    def __init__(self):
        self._cache: Dict[str, CachedTick] = {}
        self._lock = RLock()
        self._last_update_ts = 0.0
        
    def update_tick(self, symbol: str, mid: Optional[float] = None, 
                   spread_bps: Optional[float] = None, obi: Optional[float] = None):
        """Update tick data for a symbol."""
        with self._lock:
            now = time.time()
            self._last_update_ts = now
            
            if symbol not in self._cache:
                self._cache[symbol] = CachedTick(
                    mid=None,
                    spread_bps=None,
                    obi=None,
                    last_tick_ts=0.0,
                    symbol=symbol
                )
            
            tick = self._cache[symbol]
            if mid is not None:
                tick.mid = mid
            if spread_bps is not None:
                tick.spread_bps = spread_bps
            if obi is not None:
                tick.obi = obi
            tick.last_tick_ts = now
            
            logger.debug(f"Updated cache for {symbol}: mid={mid}, spread={spread_bps}bps, obi={obi}")
    
    def get_cached(self, symbol: str) -> Optional[CachedTick]:
        """Get cached data for symbol (non-blocking)."""
        with self._lock:
            return self._cache.get(symbol)
    
    def get_all_cached(self) -> Dict[str, CachedTick]:
        """Get all cached data (non-blocking)."""
        with self._lock:
            return self._cache.copy()
    
    def get_last_update_ts(self) -> float:
        """Get timestamp of last update."""
        with self._lock:
            return self._last_update_ts
    
    def is_stale(self, symbol: str, max_age_sec: float = 5.0) -> bool:
        """Check if cached data is stale."""
        with self._lock:
            tick = self._cache.get(symbol)
            if not tick:
                return True
            return (time.time() - tick.last_tick_ts) > max_age_sec

# Global cache instance
_market_cache = MarketCache()

def get_market_cache() -> MarketCache:
    """Get the global market cache."""
    return _market_cache

def update_tick(symbol: str, mid: Optional[float] = None, 
                spread_bps: Optional[float] = None, obi: Optional[float] = None):
    """Update tick data in global cache."""
    _market_cache.update_tick(symbol, mid, spread_bps, obi)

def get_cached(symbol: str) -> Optional[CachedTick]:
    """Get cached data for symbol (non-blocking)."""
    return _market_cache.get_cached(symbol)
