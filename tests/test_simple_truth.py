"""
Simple Deterministic Tests - Phase ε.0 Integrity Review
Tests that core modules produce stable, predictable outputs.
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_reasoning_determinism():
    """Test that ReasoningEngine produces identical outputs for identical inputs."""
    try:
        from backend.agents.reasoning_engine import ReasoningEngine
        
        engine = ReasoningEngine()
        snap = {
            "symbol": "BTC",
            "price": 42000,
            "price_change_24h": 1000,
            "funding_rate": 0.01,
            "open_interest": 1.2,
            "volume_24h": 1000,
            "spread_bps": 0.2
        }
        
        # Test deterministic output
        result1 = asyncio.run(engine.analyze(snap))
        result2 = asyncio.run(engine.analyze(snap))
        
        # Should be identical (excluding timestamps)
        assert result1["symbol"] == result2["symbol"]
        assert result1["trend_bias"] == result2["trend_bias"]
        assert result1["confidence"] == result2["confidence"]
        assert result1["rationale"] == result2["rationale"]
        print("✅ ReasoningEngine determinism test passed")
        return True
    except Exception as e:
        print(f"❌ ReasoningEngine determinism test failed: {e}")
        return False

def test_trade_kernel_guard():
    """Test that TradeKernel properly guards against low confidence trades."""
    try:
        from backend.agents.trade_kernel import TradeKernel
        
        tk = TradeKernel()
        
        # Test low confidence trade (should be rejected)
        decision = {
            "symbol": "BTC",
            "side": "buy",
            "size": 0.1,
            "confidence": 0.4,  # Below threshold
            "rationale": "Low confidence test",
            "price": 42000
        }
        
        result = asyncio.run(tk.execute(decision))
        assert result["status"] == "skipped"
        assert "Low confidence" in result["reason"]
        print("✅ TradeKernel guard test passed")
        return True
    except Exception as e:
        print(f"❌ TradeKernel guard test failed: {e}")
        return False

def test_order_intent_validation():
    """Test that OrderIntent validation is deterministic."""
    try:
        from backend.schemas.order_intent import create_order_intent, validate_order_intent
        
        # Test valid order
        order = create_order_intent(
            symbol="BTC",
            side="BUY",
            size=1.0,
            order_type="market"
        )
        
        result1 = validate_order_intent(order)
        result2 = validate_order_intent(order)
        
        assert result1.valid == result2.valid
        assert result1.errors == result2.errors
        assert result1.warnings == result2.warnings
        print("✅ OrderIntent validation test passed")
        return True
    except Exception as e:
        print(f"❌ OrderIntent validation test failed: {e}")
        return False

def test_idempotency_cache():
    """Test that IdempotencyCache behaves deterministically."""
    try:
        from backend.exchange.order_bus import IdempotencyCache
        
        cache = IdempotencyCache(window_seconds=60, max_size=10)
        
        intent_id = "test-intent-123"
        order_data = {"symbol": "BTC", "side": "BUY", "size": 1.0}
        
        # First call should not be idempotent
        result1 = asyncio.run(cache.check_and_store(intent_id, order_data))
        assert result1 == False
        
        # Second call should be idempotent
        result2 = asyncio.run(cache.check_and_store(intent_id, order_data))
        assert result2 == True
        print("✅ IdempotencyCache test passed")
        return True
    except Exception as e:
        print(f"❌ IdempotencyCache test failed: {e}")
        return False

def test_hl_private_client_dry_run():
    """Test that HLPrivateClient dry-run mode is deterministic."""
    try:
        from backend.exchange.hl_private import hl_private_client
        
        order_intent = {
            "symbol": "BTC",
            "side": "BUY",
            "size": 1.0,
            "type": "market",
            "intent_id": "test-123"
        }
        
        # Build order (should be deterministic)
        payload1 = hl_private_client.build_order(order_intent)
        payload2 = hl_private_client.build_order(order_intent)
        
        # Should have same structure (excluding timestamps and signatures)
        assert payload1["action"] == payload2["action"]
        assert payload1["intent_id"] == payload2["intent_id"]
        assert "signature" in payload1
        assert "signature" in payload2
        print("✅ HLPrivateClient dry-run test passed")
        return True
    except Exception as e:
        print(f"❌ HLPrivateClient dry-run test failed: {e}")
        return False

def main():
    """Run all deterministic tests."""
    print("=== Phase ε.0: Deterministic Output Tests ===")
    
    tests = [
        test_reasoning_determinism,
        test_trade_kernel_guard,
        test_order_intent_validation,
        test_idempotency_cache,
        test_hl_private_client_dry_run
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n=== Results: {passed}/{total} tests passed ===")
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
