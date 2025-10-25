#!/usr/bin/env python3
"""
Hyperliquid test order script for push-button testing.
Tests agent approval, price fetching, and order placement.
"""
import asyncio
import httpx
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from common.config import load_config


async def test_agent_status():
    """Test agent approval status."""
    print("🔍 Checking agent approval status...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("http://localhost:8000/agent_status")
            if resp.status_code == 200:
                data = resp.json()
                print(f"   Master: {data['master']}")
                print(f"   API Wallet: {data['api_wallet']}")
                print(f"   Approved: {data['approved']}")
                if not data['approved']:
                    print("   ❌ Agent not approved! Please approve in Hyperliquid UI.")
                    return False
                print("   ✅ Agent approved!")
                return True
            else:
                print(f"   ❌ Failed to check agent status: {resp.status_code}")
                return False
        except Exception as e:
            print(f"   ❌ Error checking agent status: {e}")
            return False


async def test_signer_checks():
    """Test signer consistency."""
    print("🔍 Checking signer consistency...")
    async with httpx.AsyncClient() as client:
        try:
            # Check signer_check
            resp1 = await client.get("http://localhost:8000/signer_check")
            if resp1.status_code == 200:
                data1 = resp1.json()
                print(f"   Signer Check - Match: {data1['match']}")
            else:
                print(f"   ❌ Signer check failed: {resp1.status_code}")
                return False
            
            # Check whoami_trade
            resp2 = await client.get("http://localhost:8000/whoami_trade")
            if resp2.status_code == 200:
                data2 = resp2.json()
                print(f"   Whoami Trade - Match: {data2['match']}")
            else:
                print(f"   ❌ Whoami trade failed: {resp2.status_code}")
                return False
            
            if data1['match'] and data2['match']:
                print("   ✅ Signer checks passed!")
                return True
            else:
                print("   ❌ Signer mismatch detected!")
                return False
        except Exception as e:
            print(f"   ❌ Error checking signers: {e}")
            return False


async def test_price_probe(symbol="HYPE"):
    """Test price fetching."""
    print(f"🔍 Testing price probe for {symbol}...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"http://localhost:8000/debug_book?symbol={symbol}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"   Bid: {data['bid']}")
                print(f"   Ask: {data['ask']}")
                print("   ✅ Price probe successful!")
                return True
            else:
                print(f"   ❌ Price probe failed: {resp.status_code}")
                return False
        except Exception as e:
            print(f"   ❌ Error in price probe: {e}")
            return False


async def test_tiny_trade(symbol="HYPE", side="LONG", usd=1.0):
    """Test tiny trade execution."""
    print(f"🔍 Testing tiny trade: {symbol} {side} ${usd}...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"http://localhost:8000/trade_test",
                params={
                    "symbol": symbol,
                    "side": side,
                    "usd": usd,
                    "dry_run": False,
                    "hold_seconds": 3
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
                print("   ✅ Trade test completed!")
                return True
            else:
                print(f"   ❌ Trade test failed: {resp.status_code}")
                print(f"   Response: {resp.text}")
                return False
        except Exception as e:
            print(f"   ❌ Error in trade test: {e}")
            return False


async def main():
    """Run all tests in sequence."""
    print("🚀 Hyperliquid Test Order Script")
    print("=" * 50)
    
    # Load config to show environment
    try:
        cfg = load_config()
        print(f"Environment: {cfg.hl.env}")
        print(f"Master: {cfg.hl.account}")
        print(f"API Wallet: {cfg.hl.api_wallet}")
        print()
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return
    
    # Run tests
    tests = [
        ("Agent Status", test_agent_status),
        ("Signer Checks", test_signer_checks),
        ("Price Probe", test_price_probe),
        ("Tiny Trade", test_tiny_trade),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n📋 {name}")
        print("-" * 30)
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"   ❌ Test failed with exception: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:20} {status}")
        if result:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(results)}")
    
    if passed == len(results):
        print("🎉 All tests passed! System is ready for trading.")
    else:
        print("⚠️  Some tests failed. Please check the issues above.")


if __name__ == "__main__":
    asyncio.run(main())
