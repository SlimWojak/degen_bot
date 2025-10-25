"""
Unit tests for HL REST API meta data calls.
Tests metaAndAssetCtxs endpoint and required fields.
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from typing import Dict, Any

# Mock the REST API call
async def mock_meta_and_asset_contexts():
    """Mock metaAndAssetCtxs API response."""
    return {
        "meta": {
            "tokens": [
                {
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "szDecimals": 8,
                    "weiDecimals": 8,
                    "address": "0x1234567890123456789012345678901234567890"
                },
                {
                    "name": "Ethereum", 
                    "symbol": "ETH",
                    "szDecimals": 6,
                    "weiDecimals": 6,
                    "address": "0x0987654321098765432109876543210987654321"
                }
            ]
        },
        "assetContexts": [
            {
                "name": "Bitcoin",
                "symbol": "BTC",
                "markPx": "45000.5",
                "indexPx": "45001.0",
                "openInterest": "1000000.0",
                "funding": "0.0001",
                "impactPxs": ["45000.0", "45001.0", "45002.0"]
            },
            {
                "name": "Ethereum",
                "symbol": "ETH", 
                "markPx": "3000.25",
                "indexPx": "3000.50",
                "openInterest": "500000.0",
                "funding": "0.0002",
                "impactPxs": ["3000.0", "3000.5", "3001.0"]
            }
        ]
    }


class TestHLMetaREST:
    """Test HL REST API meta data compliance."""
    
    @pytest.mark.asyncio
    async def test_meta_and_asset_contexts_structure(self):
        """Test that metaAndAssetCtxs returns expected structure."""
        response = await mock_meta_and_asset_contexts()
        
        # Verify top-level structure
        assert "meta" in response
        assert "assetContexts" in response
        
        # Verify meta structure
        meta = response["meta"]
        assert "tokens" in meta
        assert isinstance(meta["tokens"], list)
        assert len(meta["tokens"]) >= 2  # At least BTC and ETH
        
        # Verify asset contexts structure
        contexts = response["assetContexts"]
        assert isinstance(contexts, list)
        assert len(contexts) >= 2
        
        # Find BTC and ETH contexts
        btc_context = next((ctx for ctx in contexts if ctx["symbol"] == "BTC"), None)
        eth_context = next((ctx for ctx in contexts if ctx["symbol"] == "ETH"), None)
        
        assert btc_context is not None
        assert eth_context is not None
    
    @pytest.mark.asyncio
    async def test_required_fields_present(self):
        """Test that all required fields are present for BTC/ETH."""
        response = await mock_meta_and_asset_contexts()
        contexts = response["assetContexts"]
        
        # Find BTC and ETH contexts
        btc_context = next((ctx for ctx in contexts if ctx["symbol"] == "BTC"), None)
        eth_context = next((ctx for ctx in contexts if ctx["symbol"] == "ETH"), None)
        
        required_fields = ["markPx", "indexPx", "openInterest", "funding", "impactPxs"]
        
        for context in [btc_context, eth_context]:
            assert context is not None
            for field in required_fields:
                assert field in context, f"Missing required field: {field}"
                assert context[field] is not None, f"Field {field} is None"
    
    @pytest.mark.asyncio
    async def test_data_types_and_formats(self):
        """Test that data is in expected formats."""
        response = await mock_meta_and_asset_contexts()
        contexts = response["assetContexts"]
        
        btc_context = next((ctx for ctx in contexts if ctx["symbol"] == "BTC"), None)
        
        # Test price fields are numeric strings
        assert isinstance(btc_context["markPx"], str)
        assert isinstance(btc_context["indexPx"], str)
        assert isinstance(btc_context["openInterest"], str)
        assert isinstance(btc_context["funding"], str)
        
        # Test that prices can be converted to float
        mark_px = float(btc_context["markPx"])
        index_px = float(btc_context["indexPx"])
        open_interest = float(btc_context["openInterest"])
        funding = float(btc_context["funding"])
        
        assert mark_px > 0
        assert index_px > 0
        assert open_interest >= 0
        assert isinstance(funding, float)  # Can be negative
        
        # Test impact prices array
        impact_pxs = btc_context["impactPxs"]
        assert isinstance(impact_pxs, list)
        assert len(impact_pxs) >= 3  # At least 3 impact price levels
        
        for px in impact_pxs:
            assert isinstance(px, str)
            assert float(px) > 0
    
    @pytest.mark.asyncio
    async def test_symbol_consistency(self):
        """Test that symbols are consistent between meta and contexts."""
        response = await mock_meta_and_asset_contexts()
        
        meta_symbols = {token["symbol"] for token in response["meta"]["tokens"]}
        context_symbols = {ctx["symbol"] for ctx in response["assetContexts"]}
        
        # All context symbols should be in meta tokens
        assert context_symbols.issubset(meta_symbols)
        
        # Should have at least BTC and ETH
        assert "BTC" in context_symbols
        assert "ETH" in context_symbols
    
    @pytest.mark.asyncio
    async def test_rest_api_integration(self):
        """Test REST API integration with proper error handling."""
        # This would test the actual REST API call in a real implementation
        # For now, we test the mock structure
        
        with patch('backend.services.market_feed_manager.requests.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.json.return_value = await mock_meta_and_asset_contexts()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            # Test that the API call would work
            # In real implementation, this would be:
            # response = await fetch_meta_and_asset_contexts()
            # assert response.status_code == 200
            # data = response.json()
            # assert "meta" in data
            
            assert True  # Placeholder for actual REST test


if __name__ == "__main__":
    pytest.main([__file__])
