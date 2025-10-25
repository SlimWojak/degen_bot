"""
Unit tests for idempotency cache and order bus.
Tests order deduplication, cache expiration, and audit logging.
"""

import pytest
import asyncio
import time
from datetime import datetime, timezone
from backend.exchange.order_bus import IdempotencyCache, OrderBus
from backend.schemas.order_intent import create_order_intent

class TestIdempotencyCache:
    """Test idempotency cache functionality."""
    
    @pytest.mark.asyncio
    async def test_cache_basic_operations(self):
        """Test basic cache operations."""
        cache = IdempotencyCache(window_seconds=60, max_size=10)
        
        intent_id = "test-intent-123"
        order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
        
        # First submission should not be idempotent
        is_idempotent = await cache.check_and_store(intent_id, order_data)
        assert not is_idempotent
        
        # Second submission should be idempotent
        is_idempotent = await cache.check_and_store(intent_id, order_data)
        assert is_idempotent
    
    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Test cache expiration."""
        cache = IdempotencyCache(window_seconds=1, max_size=10)  # 1 second window
        
        intent_id = "test-intent-123"
        order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
        
        # First submission
        is_idempotent = await cache.check_and_store(intent_id, order_data)
        assert not is_idempotent
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Should not be idempotent after expiration
        is_idempotent = await cache.check_and_store(intent_id, order_data)
        assert not is_idempotent
    
    @pytest.mark.asyncio
    async def test_cache_max_size(self):
        """Test cache max size enforcement."""
        cache = IdempotencyCache(window_seconds=60, max_size=3)
        
        # Add more than max_size entries
        for i in range(5):
            intent_id = f"test-intent-{i}"
            order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
            await cache.check_and_store(intent_id, order_data)
        
        # Cache should only contain max_size entries
        assert len(cache.cache) == 3
        
        # Oldest entries should be evicted
        assert "test-intent-0" not in cache.cache
        assert "test-intent-1" not in cache.cache
        assert "test-intent-2" in cache.cache
        assert "test-intent-3" in cache.cache
        assert "test-intent-4" in cache.cache
    
    @pytest.mark.asyncio
    async def test_cache_get_operation(self):
        """Test cache get operation."""
        cache = IdempotencyCache(window_seconds=60, max_size=10)
        
        intent_id = "test-intent-123"
        order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
        
        # Store data
        await cache.check_and_store(intent_id, order_data)
        
        # Retrieve data
        retrieved = await cache.get(intent_id)
        assert retrieved is not None
        assert retrieved["order_data"] == order_data
        assert "timestamp" in retrieved
        assert "created_at" in retrieved
        
        # Test non-existent key
        retrieved = await cache.get("non-existent")
        assert retrieved is None

class TestOrderBus:
    """Test order bus functionality."""
    
    @pytest.mark.asyncio
    async def test_order_submission(self):
        """Test order submission to bus."""
        bus = OrderBus()
        
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            intent_id="test-intent-123"
        )
        
        result = await bus.submit(order_intent)
        
        assert result.success
        assert result.order_id is not None
        assert not result.idempotent
        assert result.validation_result is not None
        assert result.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_idempotent_submission(self):
        """Test idempotent order submission."""
        bus = OrderBus()
        
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            intent_id="test-intent-123"
        )
        
        # First submission
        result1 = await bus.submit(order_intent)
        assert result1.success
        assert not result1.idempotent
        
        # Second submission with same intent_id
        result2 = await bus.submit(order_intent)
        assert not result2.success
        assert result2.idempotent
        assert "already processed" in result2.error_message
    
    @pytest.mark.asyncio
    async def test_invalid_order_submission(self):
        """Test invalid order submission."""
        bus = OrderBus()
        
        # Create invalid order (negative size)
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=-1.0,  # Invalid size
            intent_id="test-intent-invalid"
        )
        
        result = await bus.submit(order_intent)
        
        assert not result.success
        assert not result.idempotent
        assert result.validation_result is not None
        assert not result.validation_result.valid
        assert len(result.validation_result.errors) > 0
    
    @pytest.mark.asyncio
    async def test_order_status_update(self):
        """Test order status update."""
        bus = OrderBus()
        
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            intent_id="test-intent-123"
        )
        
        # Submit order
        result = await bus.submit(order_intent)
        assert result.success
        
        order_id = result.order_id
        
        # Update status
        await bus.update_order_status(order_id, "submitted", {"mode": "sim"})
        
        # Check order in pending orders
        order = bus.get_order_by_id(order_id)
        assert order is not None
        assert order["status"] == "submitted"
        assert order["mode"] == "sim"
    
    @pytest.mark.asyncio
    async def test_pending_orders_retrieval(self):
        """Test pending orders retrieval."""
        bus = OrderBus()
        
        # Submit multiple orders
        for i in range(3):
            order_intent = create_order_intent(
                symbol="BTC",
                side="BUY",
                size=1.0,
                intent_id=f"test-intent-{i}"
            )
            await bus.submit(order_intent)
        
        # Get pending orders
        pending_orders = bus.get_pending_orders(limit=10)
        assert len(pending_orders) == 3
        
        # Test limit
        pending_orders = bus.get_pending_orders(limit=2)
        assert len(pending_orders) == 2
    
    @pytest.mark.asyncio
    async def test_audit_logging(self):
        """Test audit logging functionality."""
        bus = OrderBus()
        
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            intent_id="test-intent-123"
        )
        
        # Submit order (should log audit event)
        result = await bus.submit(order_intent)
        assert result.success
        
        # Get audit trail
        audit_events = bus.get_audit_tail(lines=10)
        assert len(audit_events) > 0
        
        # Check audit event structure
        event = audit_events[-1]  # Last event
        assert event["event"] == "order_submitted"
        assert event["intent_id"] == "test-intent-123"
        assert event["symbol"] == "BTC"
        assert event["side"] == "BUY"
        assert event["size"] == 1.0
        assert "timestamp" in event
    
    @pytest.mark.asyncio
    async def test_order_lookup(self):
        """Test order lookup by ID and intent ID."""
        bus = OrderBus()
        
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            intent_id="test-intent-123"
        )
        
        # Submit order
        result = await bus.submit(order_intent)
        assert result.success
        
        order_id = result.order_id
        intent_id = order_intent.intent_id
        
        # Lookup by order ID
        order_by_id = bus.get_order_by_id(order_id)
        assert order_by_id is not None
        assert order_by_id["intent_id"] == intent_id
        
        # Lookup by intent ID
        order_by_intent = bus.get_order_by_intent_id(intent_id)
        assert order_by_intent is not None
        assert order_by_intent["intent_id"] == intent_id
        
        # Test non-existent lookups
        assert bus.get_order_by_id("non-existent") is None
        assert bus.get_order_by_intent_id("non-existent") is None

class TestOrderBusIntegration:
    """Test order bus integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_full_order_lifecycle(self):
        """Test complete order lifecycle."""
        bus = OrderBus()
        
        # Create order intent
        order_intent = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            intent_id="test-intent-123"
        )
        
        # Submit order
        result = await bus.submit(order_intent)
        assert result.success
        
        order_id = result.order_id
        
        # Update status to submitted
        await bus.update_order_status(order_id, "submitted", {"mode": "sim"})
        
        # Update status to filled
        await bus.update_order_status(order_id, "filled", {
            "filled_size": 1.0,
            "remaining_size": 0.0,
            "execution_price": 50000.0
        })
        
        # Check final order state
        order = bus.get_order_by_id(order_id)
        assert order["status"] == "filled"
        assert order["filled_size"] == 1.0
        assert order["remaining_size"] == 0.0
        assert order["execution_price"] == 50000.0
    
    @pytest.mark.asyncio
    async def test_concurrent_submissions(self):
        """Test concurrent order submissions."""
        bus = OrderBus()
        
        async def submit_order(i):
            order_intent = create_order_intent(
                symbol="BTC",
                side="BUY",
                size=1.0,
                intent_id=f"test-intent-{i}"
            )
            return await bus.submit(order_intent)
        
        # Submit multiple orders concurrently
        tasks = [submit_order(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        for result in results:
            assert result.success
            assert result.order_id is not None
        
        # Check pending orders
        pending_orders = bus.get_pending_orders()
        assert len(pending_orders) == 5
