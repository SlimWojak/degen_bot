"""
Idempotency Cache Tests - Phase ε.1 Purification Pass
Tests for IdempotencyCache TTL + eviction semantics with deterministic behavior.
"""

import pytest
import asyncio
import time
from datetime import datetime, timezone, timedelta

from backend.exchange.order_bus import IdempotencyCache
from backend.util.async_tools import get_deterministic_clock, seeded_random


@pytest.mark.asyncio
@pytest.mark.deterministic
class TestIdempotencyCache:
    """Test IdempotencyCache with deterministic TTL and eviction behavior."""
    
    async def test_ttl_eviction_deterministic(self, deterministic_time):
        """Test that TTL-based eviction is deterministic with frozen time."""
        clock = deterministic_time
        clock.freeze()
        base_time = clock.time()
        
        # Create cache with short TTL for testing
        cache = IdempotencyCache(window_seconds=5, max_size=10)
        
        # Add item
        intent_id = "test-intent-123"
        order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
        
        # First call should not be idempotent
        result1 = await cache.check_and_store(intent_id, order_data)
        assert result1 is False
        
        # Second call should be idempotent
        result2 = await cache.check_and_store(intent_id, order_data)
        assert result2 is True
        
        # Advance time beyond TTL
        clock.advance(6.0)  # 6 seconds > 5 second TTL
        
        # Should no longer be idempotent (evicted)
        result3 = await cache.check_and_store(intent_id, order_data)
        assert result3 is False
    
    async def test_lru_eviction_deterministic(self, deterministic_time):
        """Test that LRU eviction is deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        # Create cache with small max size
        cache = IdempotencyCache(window_seconds=60, max_size=3)
        
        # Add items in order
        for i in range(5):
            intent_id = f"intent-{i}"
            order_data = {"symbol": "BTC", "side": "BUY", "size": float(i)}
            
            result = await cache.check_and_store(intent_id, order_data)
            assert result is False  # First time, not idempotent
        
        # Check that oldest items were evicted
        # Items 0, 1 should be evicted (LRU)
        # Items 2, 3, 4 should still be cached
        
        for i in range(5):
            intent_id = f"intent-{i}"
            order_data = {"symbol": "BTC", "side": "BUY", "size": float(i)}
            
            result = await cache.check_and_store(intent_id, order_data)
            if i < 2:  # Items 0, 1 should be evicted
                assert result is False
            else:  # Items 2, 3, 4 should be cached
                assert result is True
    
    @seeded_random(1337)
    async def test_cache_behavior_with_seeded_randomness(self):
        """Test cache behavior with seeded randomness for deterministic results."""
        cache = IdempotencyCache(window_seconds=60, max_size=10)
        
        # Generate deterministic random intent IDs
        import random
        intent_ids = [f"intent-{random.randint(1000, 9999)}" for _ in range(5)]
        
        # Add items with deterministic random data
        for intent_id in intent_ids:
            order_data = {
                "symbol": "BTC",
                "side": random.choice(["BUY", "SELL"]),
                "size": random.uniform(0.1, 1.0)
            }
            
            result = await cache.check_and_store(intent_id, order_data)
            assert result is False  # First time, not idempotent
        
        # Verify all items are cached
        for intent_id in intent_ids:
            order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
            result = await cache.check_and_store(intent_id, order_data)
            assert result is True  # Should be idempotent
    
    async def test_concurrent_access_deterministic(self, deterministic_time):
        """Test that concurrent cache access is deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        cache = IdempotencyCache(window_seconds=60, max_size=10)
        
        async def add_item(intent_id: str, delay: float):
            await asyncio.sleep(delay)
            order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
            return await cache.check_and_store(intent_id, order_data)
        
        # Run concurrent additions
        tasks = [
            add_item("intent-1", 0.0),
            add_item("intent-2", 0.1),
            add_item("intent-3", 0.2),
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should be False (first time)
        assert all(result is False for result in results)
        
        # Verify all items are cached
        for intent_id in ["intent-1", "intent-2", "intent-3"]:
            order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
            result = await cache.check_and_store(intent_id, order_data)
            assert result is True  # Should be idempotent
    
    async def test_cache_size_bounds_deterministic(self, deterministic_time):
        """Test that cache size bounds are deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        cache = IdempotencyCache(window_seconds=60, max_size=3)
        
        # Add more items than max_size
        for i in range(5):
            intent_id = f"intent-{i}"
            order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
            await cache.check_and_store(intent_id, order_data)
        
        # Cache should not exceed max_size
        assert len(cache._cache) <= 3
    
    async def test_ttl_refresh_deterministic(self, deterministic_time):
        """Test that TTL refresh is deterministic."""
        clock = deterministic_time
        clock.freeze()
        base_time = clock.time()
        
        cache = IdempotencyCache(window_seconds=10, max_size=10)
        
        # Add item
        intent_id = "test-intent"
        order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
        
        await cache.check_and_store(intent_id, order_data)
        
        # Advance time by 5 seconds (within TTL)
        clock.advance(5.0)
        
        # Access item to refresh TTL
        result = await cache.check_and_store(intent_id, order_data)
        assert result is True  # Should still be cached
        
        # Advance time by another 5 seconds (total 10, at TTL boundary)
        clock.advance(5.0)
        
        # Should still be cached due to refresh
        result = await cache.check_and_store(intent_id, order_data)
        assert result is True
        
        # Advance time by 1 more second (beyond TTL)
        clock.advance(1.0)
        
        # Should be evicted
        result = await cache.check_and_store(intent_id, order_data)
        assert result is False
    
    async def test_multiple_symbols_deterministic(self, deterministic_time):
        """Test cache behavior with multiple symbols is deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        cache = IdempotencyCache(window_seconds=60, max_size=10)
        
        # Add items for different symbols
        symbols = ["BTC", "ETH", "SOL"]
        for symbol in symbols:
            intent_id = f"intent-{symbol}"
            order_data = {"symbol": symbol, "side": "BUY", "size": 1.0}
            
            result = await cache.check_and_store(intent_id, order_data)
            assert result is False  # First time
        
        # Verify all symbols are cached
        for symbol in symbols:
            intent_id = f"intent-{symbol}"
            order_data = {"symbol": symbol, "side": "BUY", "size": 1.0}
            
            result = await cache.check_and_store(intent_id, order_data)
            assert result is True  # Should be idempotent
