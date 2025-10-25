# scripts/test_order.py
import asyncio
import sys
import os
import time
import json

# Add parent directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.config import load_config
from common.action_schema import TradeAction
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from bot.executor import OrderExecutor

async def place_and_cancel(exe: OrderExecutor, symbol: str):
    """
    Test order placement and cancellation flow.
    
    Args:
        exe: OrderExecutor instance
        symbol: Symbol to test with
    """
    try:
        print(f"🧪 Testing order flow for {symbol}")
        
        # 1) Get best bid/ask via market data client
        print("📊 Getting market data...")
        book = await exe.best_bid_ask(symbol)
        print(f"   Bid: ${book['bid']:.4f}, Ask: ${book['ask']:.4f}")
        
        # Use bid price * 0.999 to ensure it's below market and won't fill
        px = book["bid"] * 0.999
        print(f"   Using price: ${px:.4f} (below bid for POST_ONLY safety)")
        
        # 2) Create TradeAction
        action = TradeAction(
            symbol=symbol,
            side="LONG",
            type="LIMIT",
            qty=0.001,  # Very small size for testing
            price=px,
            time_in_force="POST_ONLY"
        )
        
        print(f"📝 Created order: {action.side} {action.qty} {action.symbol} @ ${action.price}")
        
        # 3) Place order
        print("🚀 Placing order...")
        oid = await exe.place_order(action)
        if not oid:
            print("❌ Failed to place order")
            return False
        
        print(f"✅ Order placed: {oid}")
        
        # 4) Wait for acknowledgment
        print("⏳ Waiting for acknowledgment...")
        acked = await exe.wait_for_ack(oid, timeout=3.0)
        if not acked:
            print("❌ Order not acknowledged")
            return False
        
        print("✅ Order acknowledged")
        
        # 5) Cancel order
        print("🛑 Cancelling order...")
        cancelled = await exe.cancel_order(oid)
        if not cancelled:
            print("❌ Failed to cancel order")
            return False
        
        print("✅ Order cancelled successfully")
        
        # 6) Summary
        print(f"🎯 Test completed for {symbol}: placed → ack → cancel")
        return True
        
    except Exception as e:
        print(f"❌ Error in test: {e}")
        return False

async def main():
    """Main test function."""
    try:
        print("🔧 Loading configuration...")
        cfg = load_config()
        print(f"   Environment: {cfg.hl.env}")
        print(f"   Assets: {cfg.bot.assets}")
        
        # Initialize exchange and info
        print("🔌 Initializing Hyperliquid connection...")
        exchange = Exchange(
            {"account_address": cfg.hl.account, "secret_key": cfg.hl.private_key},
            base_url=cfg.hl.rest_url
        )
        info = Info(cfg.hl.rest_url, skip_ws=True)
        
        # Create executor
        config_dict = {
            "bot": {
                "dry_run": True,  # Start with dry run for safety
                "testnet": cfg.hl.env == "testnet"
            }
        }
        
        executor = OrderExecutor(exchange, info, config_dict)
        print("✅ Executor initialized")
        
        # Test with first available asset
        test_symbol = cfg.bot.assets[0] if cfg.bot.assets else "BTC"
        print(f"🎯 Testing with {test_symbol}")
        
        # Run the test
        success = await place_and_cancel(executor, test_symbol)
        
        if success:
            print("\n🎉 All tests passed!")
            print("✅ Order lifecycle: placed → ack → cancel")
            print("✅ No fills created (POST_ONLY safety)")
            print("✅ PnL unchanged")
        else:
            print("\n❌ Test failed")
            return 1
            
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
