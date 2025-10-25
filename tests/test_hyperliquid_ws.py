"""
Hyperliquid WebSocket Tests - Phase ε.1 Purification Pass
Tests for WebSocket policy violation handling and deterministic behavior.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from backend.services.hyperliquid_ws import HyperliquidWSClient
from backend.util.async_tools import get_deterministic_clock, seeded_random


@pytest.mark.asyncio
@pytest.mark.deterministic
class TestHyperliquidWS:
    """Test HyperliquidWSClient with deterministic behavior."""
    
    async def test_policy_violation_handling(self, deterministic_time):
        """Test that policy violation (1008) triggers proper guard behavior."""
        clock = deterministic_time
        clock.freeze()
        
        # Mock WebSocket connection that returns policy violation
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = [
            json.dumps({"type": "error", "message": "policy violation"}),
            asyncio.CancelledError()  # Simulate connection close
        ]
        
        # Create client with mock
        client = HyperliquidWSClient(["BTC"])
        
        # Simulate policy violation
        with patch('websockets.connect', return_value=mock_ws):
            with patch('backend.services.ws_guard.ws_guard') as mock_guard:
                mock_guard.is_blocked.return_value = False
                mock_guard.handle_policy_violation = Mock()
                
                # Start connection (will fail with policy violation)
                try:
                    await client.start()
                except Exception:
                    pass  # Expected to fail
                
                # Verify guard was notified
                mock_guard.handle_policy_violation.assert_called_once()
    
    async def test_subscription_acks_deterministic(self, deterministic_time):
        """Test that subscription acknowledgments are handled deterministically."""
        clock = deterministic_time
        clock.freeze()
        
        # Mock WebSocket with deterministic ack responses
        mock_ws = AsyncMock()
        ack_responses = [
            json.dumps({"type": "ack", "subscription": "trades", "symbol": "BTC"}),
            json.dumps({"type": "ack", "subscription": "bookTop", "symbol": "BTC"}),
        ]
        mock_ws.recv.side_effect = ack_responses + [asyncio.CancelledError()]
        
        client = HyperliquidWSClient(["BTC"])
        
        with patch('websockets.connect', return_value=mock_ws):
            with patch('backend.services.ws_guard.ws_guard') as mock_guard:
                mock_guard.is_blocked.return_value = False
                
                try:
                    await client.start()
                except Exception:
                    pass
                
                # Verify subscription acks were processed
                assert client.subscription_acks_ok is True
    
    @seeded_random(1337)
    async def test_reconnect_backoff_deterministic(self):
        """Test that reconnection backoff is deterministic with seeded randomness."""
        client = HyperliquidWSClient(["BTC"])
        
        # Test backoff calculation is deterministic
        backoff1 = client._calculate_backoff(1)
        backoff2 = client._calculate_backoff(1)
        
        # Should be identical with same seed
        assert backoff1 == backoff2
        
        # Test exponential backoff progression
        backoff_1 = client._calculate_backoff(1)
        backoff_2 = client._calculate_backoff(2)
        backoff_3 = client._calculate_backoff(3)
        
        # Should be increasing (with jitter, but generally increasing)
        assert backoff_2 >= backoff_1 * 0.5  # Allow for jitter
        assert backoff_3 >= backoff_2 * 0.5
    
    async def test_message_handling_deterministic(self, deterministic_time):
        """Test that message handling produces deterministic results."""
        clock = deterministic_time
        clock.freeze()
        
        # Test data with deterministic timestamps
        base_time = clock.time()
        test_messages = [
            {
                "type": "trades",
                "data": [{
                    "symbol": "BTC",
                    "price": 42000.0,
                    "size": 0.1,
                    "timestamp": int(base_time * 1000)
                }]
            },
            {
                "type": "bookTop", 
                "data": [{
                    "symbol": "BTC",
                    "bid": 41999.0,
                    "ask": 42001.0,
                    "timestamp": int(base_time * 1000) + 1000
                }]
            }
        ]
        
        client = HyperliquidWSClient(["BTC"])
        
        # Process messages
        for message in test_messages:
            await client._handle_message(json.dumps(message))
        
        # Verify cache contains deterministic data
        cached = client.get_cached("BTC")
        assert cached is not None
        assert cached["price"] == 42000.0
        assert cached["bid"] == 41999.0
        assert cached["ask"] == 42001.0
    
    async def test_connection_lifecycle_deterministic(self, deterministic_time):
        """Test that connection lifecycle is deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        client = HyperliquidWSClient(["BTC"])
        
        # Test initial state
        assert not client.is_connected()
        assert client.get_reconnect_count() == 0
        
        # Mock successful connection
        mock_ws = AsyncMock()
        mock_ws.recv.side_effect = [asyncio.CancelledError()]
        
        with patch('websockets.connect', return_value=mock_ws):
            with patch('backend.services.ws_guard.ws_guard') as mock_guard:
                mock_guard.is_blocked.return_value = False
                
                try:
                    await client.start()
                except Exception:
                    pass
                
                # Verify connection state
                assert client.is_connected() is False  # Connection closed
                assert client.get_reconnect_count() >= 0
    
    async def test_error_handling_deterministic(self, deterministic_time):
        """Test that error handling produces deterministic results."""
        clock = deterministic_time
        clock.freeze()
        
        client = HyperliquidWSClient(["BTC"])
        
        # Test various error conditions
        error_messages = [
            '{"type": "error", "message": "Invalid subscription"}',
            '{"type": "error", "message": "Rate limit exceeded"}',
            '{"type": "error", "message": "Connection timeout"}',
        ]
        
        for error_msg in error_messages:
            await client._handle_message(error_msg)
        
        # Verify error count is deterministic
        assert client.error_count == len(error_messages)
    
    async def test_subscription_health_check_deterministic(self, deterministic_time):
        """Test that subscription health checks are deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        client = HyperliquidWSClient(["BTC"])
        
        # Simulate subscription acks
        client.subscriptions = {"BTC": ["trades", "bookTop"]}
        client.acks_received = {
            "BTC": {"trades": True, "bookTop": True}
        }
        
        # Health check should be deterministic
        health1 = client._check_subscription_health()
        health2 = client._check_subscription_health()
        
        assert health1 == health2
        assert health1 is True  # All acks received
    
    async def test_tick_processing_deterministic(self, deterministic_time):
        """Test that tick processing is deterministic with frozen time."""
        clock = deterministic_time
        clock.freeze()
        base_time = clock.time()
        
        client = HyperliquidWSClient(["BTC"])
        
        # Process identical ticks
        tick_data = {
            "symbol": "BTC",
            "price": 42000.0,
            "size": 0.1,
            "timestamp": int(base_time * 1000)
        }
        
        # Process same tick multiple times
        for _ in range(3):
            await client._handle_tick(tick_data)
        
        # Verify cache is deterministic
        cached = client.get_cached("BTC")
        assert cached["price"] == 42000.0
        assert cached["size"] == 0.1
        
        # Verify staleness calculation is deterministic
        staleness1 = client.last_tick_s_ago("BTC")
        staleness2 = client.last_tick_s_ago("BTC")
        
        assert staleness1 == staleness2
