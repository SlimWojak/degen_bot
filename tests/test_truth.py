"""
Deterministic Output Tests - Phase ε.0 Integrity Review
Tests that core modules produce stable, predictable outputs.
"""

import pytest
import asyncio
from datetime import datetime, timezone

def test_reasoning_determinism():
    """Test that ReasoningEngine produces identical outputs for identical inputs."""
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
    assert result1["key_indicators"]["symbol"] == result2["key_indicators"]["symbol"]
    assert result1["key_indicators"]["price"] == result2["key_indicators"]["price"]

def test_trade_kernel_guard():
    """Test that TradeKernel properly guards against low confidence trades."""
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

def test_learning_loop_idempotence():
    """Test that LearningLoop produces identical outputs for identical inputs."""
    from backend.agents.learning_loop import LearningLoop
    
    loop = LearningLoop()
    
    # Mock trade history
    sample_trades = [
        {"symbol": "BTC", "pnl": 0.1, "timestamp": "2025-01-01T00:00:00Z"},
        {"symbol": "ETH", "pnl": -0.05, "timestamp": "2025-01-01T01:00:00Z"}
    ]
    
    # Test idempotent reflection
    result1 = asyncio.run(loop.reflect())
    result2 = asyncio.run(loop.reflect())
    
    # Should have same structure (may differ in timestamp)
    assert "status" in result1
    assert "status" in result2
    assert result1["status"] == result2["status"]

def test_order_intent_validation():
    """Test that OrderIntent validation is deterministic."""
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

def test_idempotency_cache():
    """Test that IdempotencyCache behaves deterministically."""
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
    
    # Third call should still be idempotent
    result3 = asyncio.run(cache.check_and_store(intent_id, order_data))
    assert result3 == True

def test_hl_private_client_dry_run():
    """Test that HLPrivateClient dry-run mode is deterministic."""
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

def test_peso_mind_determinism():
    """Test that PesoMind produces deterministic behavior."""
    from backend.system.peso_mind import peso_mind
    
    # Test status is deterministic
    status1 = peso_mind.get_status()
    status2 = peso_mind.get_status()
    
    assert status1["running"] == status2["running"]
    assert status1["mode"] == status2["mode"]
    assert status1["llm_provider"] == status2["llm_provider"]
    assert status1["cycle_interval_seconds"] == status2["cycle_interval_seconds"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
