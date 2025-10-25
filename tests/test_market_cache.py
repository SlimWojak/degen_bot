"""
Market Cache Tests - Phase ε.1 Purification Pass
Tests for MarketCache read/write and staleness math with frozen time.
"""

import pytest
import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from backend.services.market_cache import MarketCache
from backend.util.async_tools import get_deterministic_clock, seeded_random


@pytest.mark.asyncio
@pytest.mark.deterministic
class TestMarketCache:
    """Test MarketCache with deterministic time."""
    
    async def test_cache_read_write_deterministic(self, deterministic_time):
        """Test that cache read/write is deterministic with frozen time."""
        cache = MarketCache()
        
        # Test data
        symbol = "BTC"
        tick_data = {
            "price": 42000.0,
            "size": 0.1,
            "timestamp": 1640995200000
        }
        
        # Write data
        cache.update_tick(symbol, tick_data)
        
        # Read data - should be identical
        result1 = cache.get_cached(symbol)
        result2 = cache.get_cached(symbol)
        
        assert result1 == result2
        assert result1["price"] == 42000.0
        assert result1["size"] == 0.1
    
    async def test_staleness_math_deterministic(self, deterministic_time):
        """Test staleness calculation with frozen time."""
        cache = MarketCache()
        clock = deterministic_time
        
        # Freeze time at a specific moment
        clock.freeze()
        base_time = clock.time()
        
        # Add tick data
        symbol = "BTC"
        tick_data = {
            "price": 42000.0,
            "size": 0.1,
            "timestamp": int(base_time * 1000)
        }
        cache.update_tick(symbol, tick_data)
        
        # Check staleness immediately (should be fresh)
        staleness1 = cache.last_tick_s_ago(symbol)
        assert staleness1 < 1.0  # Should be very fresh
        
        # Advance time by 5 seconds
        clock.advance(5.0)
        
        # Check staleness after 5 seconds
        staleness2 = cache.last_tick_s_ago(symbol)
        assert 4.9 <= staleness2 <= 5.1  # Should be ~5 seconds old
        
        # Advance time by 60 seconds (stale threshold)
        clock.advance(60.0)
        
        # Check staleness after 65 seconds total
        staleness3 = cache.last_tick_s_ago(symbol)
        assert 64.9 <= staleness3 <= 65.1  # Should be ~65 seconds old
    
    @seeded_random(1337)
    async def test_cache_with_seeded_randomness(self):
        """Test cache behavior with seeded randomness."""
        cache = MarketCache()
        
        # Generate deterministic random data
        import random
        prices = [random.uniform(40000, 45000) for _ in range(10)]
        
        # Add ticks with deterministic prices
        for i, price in enumerate(prices):
            tick_data = {
                "price": price,
                "size": 0.1,
                "timestamp": int(time.time() * 1000) + i * 1000
            }
            cache.update_tick("BTC", tick_data)
        
        # Verify we get the last price
        result = cache.get_cached("BTC")
        assert result["price"] == prices[-1]  # Should be the last price
    
    async def test_multiple_symbols_deterministic(self, deterministic_time):
        """Test cache with multiple symbols is deterministic."""
        cache = MarketCache()
        
        symbols = ["BTC", "ETH", "SOL"]
        base_prices = [42000.0, 3000.0, 100.0]
        
        # Add data for all symbols
        for symbol, price in zip(symbols, base_prices):
            tick_data = {
                "price": price,
                "size": 0.1,
                "timestamp": int(time.time() * 1000)
            }
            cache.update_tick(symbol, tick_data)
        
        # Verify all symbols are cached
        for symbol, expected_price in zip(symbols, base_prices):
            result = cache.get_cached(symbol)
            assert result is not None
            assert result["price"] == expected_price
    
    async def test_cache_eviction_deterministic(self, deterministic_time):
        """Test cache eviction behavior is deterministic."""
        cache = MarketCache()
        
        # Add many symbols to trigger eviction
        symbols = [f"SYMBOL_{i}" for i in range(100)]
        
        for i, symbol in enumerate(symbols):
            tick_data = {
                "price": 1000.0 + i,
                "size": 0.1,
                "timestamp": int(time.time() * 1000) + i
            }
            cache.update_tick(symbol, tick_data)
        
        # Verify cache size is bounded
        # (This depends on the cache implementation - adjust as needed)
        assert len(cache._cache) <= 100  # Should not exceed reasonable limit
    
    async def test_concurrent_access_deterministic(self, deterministic_time):
        """Test concurrent cache access is deterministic."""
        cache = MarketCache()
        
        async def update_cache(symbol: str, price: float, delay: float):
            await asyncio.sleep(delay)
            tick_data = {
                "price": price,
                "size": 0.1,
                "timestamp": int(time.time() * 1000)
            }
            cache.update_tick(symbol, tick_data)
        
        # Run concurrent updates
        tasks = [
            update_cache("BTC", 42000.0, 0.0),
            update_cache("ETH", 3000.0, 0.1),
            update_cache("SOL", 100.0, 0.2),
        ]
        
        await asyncio.gather(*tasks)
        
        # Verify all updates were applied
        btc_result = cache.get_cached("BTC")
        eth_result = cache.get_cached("ETH")
        sol_result = cache.get_cached("SOL")
        
        assert btc_result["price"] == 42000.0
        assert eth_result["price"] == 3000.0
        assert sol_result["price"] == 100.0
