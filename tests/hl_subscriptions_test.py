"""
Unit tests for HL WebSocket subscriptions.
Tests compliant subscription format and acknowledgment handling.
"""

import asyncio
import json
import pytest
import websockets
from unittest.mock import AsyncMock, patch
from typing import Dict, Any

from backend.services.hyperliquid_ws import HyperliquidWSClient


class TestHLSubscriptions:
    """Test HL WebSocket subscription compliance."""
    
    @pytest.mark.asyncio
    async def test_subscription_format_compliance(self):
        """Test that subscription messages follow HL format exactly."""
        client = HyperliquidWSClient(["BTC", "ETH"])
        
        # Mock WebSocket connection
        mock_ws = AsyncMock()
        
        # Capture sent messages
        sent_messages = []
        
        async def mock_send(message):
            sent_messages.append(json.loads(message))
            await asyncio.sleep(0.01)  # Simulate network delay
        
        mock_ws.send = mock_send
        
        # Send subscriptions
        await client._send_subscription(mock_ws)
        
        # Verify message format
        assert len(sent_messages) == 4  # 2 symbols * 2 channels each
        
        # Check trades subscriptions
        trades_messages = [msg for msg in sent_messages if msg.get("subscription", {}).get("type") == "trades"]
        assert len(trades_messages) == 2
        
        for msg in trades_messages:
            assert msg["method"] == "subscribe"
            assert "subscription" in msg
            assert msg["subscription"]["type"] == "trades"
            assert msg["subscription"]["coin"] in ["BTC", "ETH"]
        
        # Check bookTop subscriptions
        book_messages = [msg for msg in sent_messages if msg.get("subscription", {}).get("type") == "bookTop"]
        assert len(book_messages) == 2
        
        for msg in book_messages:
            assert msg["method"] == "subscribe"
            assert "subscription" in msg
            assert msg["subscription"]["type"] == "bookTop"
            assert msg["subscription"]["coin"] in ["BTC", "ETH"]
    
    @pytest.mark.asyncio
    async def test_acknowledgment_handling(self):
        """Test that acknowledgments are properly tracked."""
        client = HyperliquidWSClient(["BTC"])
        
        # Simulate acknowledgment messages
        ack_messages = [
            {"ack": {"coin": "BTC", "channel": "trades"}},
            {"ack": {"coin": "BTC", "channel": "bookTop"}}
        ]
        
        # Process acknowledgments
        for ack_msg in ack_messages:
            client._handle_ack(ack_msg)
        
        # Verify acknowledgment tracking
        assert "BTC" in client.acks_received
        assert client.acks_received["BTC"]["trades"] is True
        assert client.acks_received["BTC"]["bookTop"] is True
        assert client.subscription_acks_ok is True
    
    @pytest.mark.asyncio
    async def test_subscription_health_check(self):
        """Test subscription health validation."""
        client = HyperliquidWSClient(["BTC", "ETH"])
        
        # Initially no acknowledgments
        assert client.subscription_acks_ok is False
        
        # Simulate partial acknowledgments
        client._handle_ack({"ack": {"coin": "BTC", "channel": "trades"}})
        client._handle_ack({"ack": {"coin": "BTC", "channel": "bookTop"}})
        client._handle_ack({"ack": {"coin": "ETH", "channel": "trades"}})
        # Missing ETH bookTop acknowledgment
        
        assert client.subscription_acks_ok is False
        
        # Complete acknowledgments
        client._handle_ack({"ack": {"coin": "ETH", "channel": "bookTop"}})
        
        assert client.subscription_acks_ok is True
    
    @pytest.mark.asyncio
    async def test_rate_limiting_compliance(self):
        """Test that rate limiting follows HL guidelines."""
        client = HyperliquidWSClient(["BTC"])
        
        # Mock rate limiter
        with patch('backend.services.hyperliquid_ws.RATE_LIMIT') as mock_limiter:
            mock_limiter.__aenter__ = AsyncMock()
            mock_limiter.__aexit__ = AsyncMock()
            
            mock_ws = AsyncMock()
            await client._send_with_rate_limit(mock_ws, {"test": "message"})
            
            # Verify rate limiter was used
            mock_limiter.__aenter__.assert_called_once()
            mock_ws.send.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
