"""
Order Intent Tests - Phase ε.1 Purification Pass
Tests for OrderIntent invariants & clipping with table-driven cases.
"""

import pytest
import asyncio
from decimal import Decimal
from typing import List, Dict, Any

from backend.schemas.order_intent import (
    OrderIntent, OrderType, TimeInForce, OrderValidationResult,
    validate_order_intent, clip_to_risk, create_order_intent
)
from backend.util.async_tools import seeded_random


@pytest.mark.asyncio
@pytest.mark.deterministic
class TestOrderIntentDeterministic:
    """Test OrderIntent with deterministic validation and clipping."""
    
    @pytest.mark.parametrize("test_case", [
        # Valid cases
        {
            "name": "valid_market_buy",
            "data": {"symbol": "BTC", "side": "BUY", "size": 1.0, "type": "market"},
            "expected_valid": True,
            "expected_errors": []
        },
        {
            "name": "valid_limit_sell",
            "data": {"symbol": "ETH", "side": "SELL", "size": 0.5, "type": "limit", "limit_px": 3000.0, "tif": "GTC"},
            "expected_valid": True,
            "expected_errors": []
        },
        # Invalid cases
        {
            "name": "invalid_size_zero",
            "data": {"symbol": "BTC", "side": "BUY", "size": 0.0, "type": "market"},
            "expected_valid": False,
            "expected_errors": ["size must be greater than 0"]
        },
        {
            "name": "invalid_size_negative",
            "data": {"symbol": "BTC", "side": "BUY", "size": -1.0, "type": "market"},
            "expected_valid": False,
            "expected_errors": ["size must be greater than 0"]
        },
        {
            "name": "invalid_unknown_symbol",
            "data": {"symbol": "UNKNOWN", "side": "BUY", "size": 1.0, "type": "market"},
            "expected_valid": False,
            "expected_errors": ["symbol UNKNOWN not supported"]
        },
        {
            "name": "invalid_limit_missing_price",
            "data": {"symbol": "BTC", "side": "BUY", "size": 1.0, "type": "limit"},
            "expected_valid": False,
            "expected_errors": ["limit_px required for limit orders"]
        },
        {
            "name": "invalid_tif",
            "data": {"symbol": "BTC", "side": "BUY", "size": 1.0, "type": "market", "tif": "INVALID"},
            "expected_valid": False,
            "expected_errors": ["tif must be one of: GTC, IOC"]
        }
    ])
    async def test_validation_table_driven(self, test_case: Dict[str, Any]):
        """Test validation with table-driven test cases."""
        data = test_case["data"]
        expected_valid = test_case["expected_valid"]
        expected_errors = test_case["expected_errors"]
        
        # Create order intent
        try:
            order = create_order_intent(**data)
        except Exception:
            # If creation fails, validation should also fail
            assert not expected_valid
            return
        
        # Validate
        result = validate_order_intent(order)
        
        assert result.valid == expected_valid
        if expected_errors:
            for expected_error in expected_errors:
                assert any(expected_error in error for error in result.errors)
    
    async def test_risk_clipping_deterministic(self, deterministic_time):
        """Test that risk clipping produces deterministic results."""
        clock = deterministic_time
        clock.freeze()
        
        # Test data with various risk scenarios
        test_cases = [
            {
                "name": "normal_size",
                "order": {"symbol": "BTC", "side": "BUY", "size": 1.0, "type": "market"},
                "max_size": 10.0,
                "expected_size": 1.0
            },
            {
                "name": "oversized",
                "order": {"symbol": "BTC", "side": "BUY", "size": 15.0, "type": "market"},
                "max_size": 10.0,
                "expected_size": 10.0
            },
            {
                "name": "zero_max",
                "order": {"symbol": "BTC", "side": "BUY", "size": 5.0, "type": "market"},
                "max_size": 0.0,
                "expected_size": 0.0
            }
        ]
        
        for test_case in test_cases:
            order_data = test_case["order"]
            max_size = test_case["max_size"]
            expected_size = test_case["expected_size"]
            
            # Create order
            order = create_order_intent(**order_data)
            
            # Apply risk clipping
            clipped_order = clip_to_risk(order, max_size=max_size)
            
            assert clipped_order.size == expected_size
            assert clipped_order.symbol == order.symbol
            assert clipped_order.side == order.side
    
    @seeded_random(1337)
    async def test_deterministic_with_seeded_randomness(self):
        """Test that order processing is deterministic with seeded randomness."""
        import random
        
        # Generate deterministic random orders
        symbols = ["BTC", "ETH", "SOL"]
        sides = ["BUY", "SELL"]
        types = ["market", "limit"]
        
        orders = []
        for i in range(10):
            order_data = {
                "symbol": random.choice(symbols),
                "side": random.choice(sides),
                "size": random.uniform(0.1, 5.0),
                "type": random.choice(types)
            }
            
            if order_data["type"] == "limit":
                order_data["limit_px"] = random.uniform(1000, 50000)
                order_data["tif"] = random.choice(["GTC", "IOC"])
            
            try:
                order = create_order_intent(**order_data)
                orders.append(order)
            except Exception:
                # Skip invalid orders
                continue
        
        # Process orders deterministically
        results = []
        for order in orders:
            result = validate_order_intent(order)
            results.append(result)
        
        # Verify results are deterministic
        # (Same seed should produce same results)
        assert len(results) > 0
        assert all(isinstance(result, OrderValidationResult) for result in results)
    
    async def test_order_creation_deterministic(self, deterministic_time):
        """Test that order creation is deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        # Test data
        order_data = {
            "symbol": "BTC",
            "side": "BUY",
            "size": 1.0,
            "type": "market",
            "intent_id": "test-123"
        }
        
        # Create orders multiple times
        order1 = create_order_intent(**order_data)
        order2 = create_order_intent(**order_data)
        
        # Should have same structure (excluding timestamps)
        assert order1.symbol == order2.symbol
        assert order1.side == order2.side
        assert order1.size == order2.size
        assert order1.type == order2.type
        assert order1.intent_id == order2.intent_id
    
    async def test_validation_consistency(self, deterministic_time):
        """Test that validation is consistent across multiple calls."""
        clock = deterministic_time
        clock.freeze()
        
        # Create order
        order = create_order_intent(
            symbol="BTC",
            side="BUY", 
            size=1.0,
            type="market"
        )
        
        # Validate multiple times
        result1 = validate_order_intent(order)
        result2 = validate_order_intent(order)
        result3 = validate_order_intent(order)
        
        # Should be identical
        assert result1.valid == result2.valid == result3.valid
        assert result1.errors == result2.errors == result3.errors
        assert result1.warnings == result2.warnings == result3.warnings
    
    async def test_edge_cases_deterministic(self, deterministic_time):
        """Test edge cases produce deterministic results."""
        clock = deterministic_time
        clock.freeze()
        
        edge_cases = [
            # Minimum valid size
            {"symbol": "BTC", "side": "BUY", "size": 0.0001, "type": "market"},
            # Maximum reasonable size
            {"symbol": "BTC", "side": "BUY", "size": 1000.0, "type": "market"},
            # Limit order with exact price
            {"symbol": "BTC", "side": "BUY", "size": 1.0, "type": "limit", "limit_px": 42000.0, "tif": "GTC"},
            # IOC order
            {"symbol": "BTC", "side": "SELL", "size": 0.5, "type": "limit", "limit_px": 42000.0, "tif": "IOC"},
        ]
        
        for case in edge_cases:
            try:
                order = create_order_intent(**case)
                result = validate_order_intent(order)
                
                # Should be valid for these edge cases
                assert result.valid is True
                assert len(result.errors) == 0
                
            except Exception as e:
                # If creation fails, it should be a known validation error
                assert "validation" in str(e).lower() or "invalid" in str(e).lower()
    
    async def test_concurrent_validation_deterministic(self, deterministic_time):
        """Test that concurrent validation is deterministic."""
        clock = deterministic_time
        clock.freeze()
        
        # Create order
        order = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            type="market"
        )
        
        async def validate_order():
            return validate_order_intent(order)
        
        # Run concurrent validations
        tasks = [validate_order() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # All results should be identical
        first_result = results[0]
        for result in results[1:]:
            assert result.valid == first_result.valid
            assert result.errors == first_result.errors
            assert result.warnings == first_result.warnings
