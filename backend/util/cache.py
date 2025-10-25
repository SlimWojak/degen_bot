"""
In-memory caching helper for state data.
Provides async caching with TTL and graceful fallback to stale data.
"""

import asyncio
import time
from typing import Any, Callable, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Global cache storage
_cache: Dict[str, Tuple[float, Any]] = {}

async def cached(key: str, ttl_ms: int, producer: Callable[[], Any]) -> Any:
    """
    Cache with TTL and graceful stale fallback.
    
    Args:
        key: Cache key
        ttl_ms: Time-to-live in milliseconds
        producer: Function to produce fresh data
        
    Returns:
        Cached data or stale data if producer fails
    """
    now = time.time() * 1000  # Convert to milliseconds
    expires_at = now + ttl_ms
    
    # Check if we have valid cached data
    if key in _cache:
        cached_expires, cached_value = _cache[key]
        if now < cached_expires:
            logger.debug(f"Cache hit for {key}")
            return cached_value
        else:
            logger.debug(f"Cache expired for {key}, refreshing")
    
    # Try to get fresh data
    try:
        if asyncio.iscoroutinefunction(producer):
            fresh_data = await producer()
        else:
            fresh_data = producer()
        _cache[key] = (expires_at, fresh_data)
        logger.debug(f"Cache updated for {key}")
        return fresh_data
    except Exception as e:
        logger.warning(f"Producer failed for {key}: {e}")
        
        # Return stale data if available
        if key in _cache:
            _, stale_value = _cache[key]
            # Add stale metadata
            if isinstance(stale_value, dict):
                stale_value = stale_value.copy()
                stale_value["_meta"] = stale_value.get("_meta", {})
                stale_value["_meta"]["stale"] = True
            logger.debug(f"Returning stale data for {key}")
            return stale_value
        
        # No stale data available, return empty with error metadata
        empty_result = {"_meta": {"error": str(e), "stale": True}}
        logger.warning(f"No cached data for {key}, returning empty")
        return empty_result

def clear_cache():
    """Clear all cached data."""
    global _cache
    _cache.clear()
    logger.info("Cache cleared")

def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    now = time.time() * 1000
    valid_entries = sum(1 for expires_at, _ in _cache.values() if now < expires_at)
    expired_entries = len(_cache) - valid_entries
    
    return {
        "total_entries": len(_cache),
        "valid_entries": valid_entries,
        "expired_entries": expired_entries,
        "keys": list(_cache.keys())
    }
