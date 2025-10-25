"""
Unified Hyperliquid WebSocket client following official documentation.
Single socket for all symbols with proper heartbeat and rate limiting.
"""

import asyncio
import json
import logging
import time
import websockets
from typing import Dict, List, Optional, Any
from asyncio import Semaphore

from backend.config import settings
from backend.services.market_cache import update_tick
from backend.services.ws_guard import ws_guard

logger = logging.getLogger("market_ws")

# Rate limiting: ≤ 20 messages/s, ≤ 100 channels/socket
RATE_LIMIT = Semaphore(20)  # 20 messages per second
HEARTBEAT_INTERVAL = 25  # seconds
MAX_BACKOFF = 30  # seconds

class HyperliquidWSClient:
    """Unified WebSocket client for Hyperliquid feed."""
    
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.ws_url = "wss://api.hyperliquid.xyz/ws"
        self.ws = None
        self.running = False
        self.connection_task = None
        
        # Connection state
        self.connected = False
        self.last_tick_ts = 0.0
        self.reconnect_count = 0
        self.last_ping_ts = 0.0
        
        # Health metrics
        self.symbols_active = set()
        self.total_ticks = 0
        self.error_count = 0
        self.pings_sent = 0
        
        # Subscription tracking
        self.subscriptions = {}  # {symbol: [channel_types]}
        self.acks_received = {}  # {symbol: {channel: bool}}
        self.subscription_acks_ok = False
        
    async def start(self) -> None:
        """Start the unified WebSocket client."""
        if self.running:
            logger.warning("[market_ws] Client already running")
            return
            
        self.running = True
        self.connection_task = asyncio.create_task(self._connection_loop())
        logger.info(f"[market_ws] Started unified client for symbols: {self.symbols}")
        
    async def stop(self) -> None:
        """Stop the WebSocket client."""
        self.running = False
        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                pass
        logger.info("[market_ws] Client stopped")
        
    async def _connection_loop(self) -> None:
        """Main connection loop with exponential backoff and policy guard."""
        backoff = 1
        
        while self.running:
            # Check if we're blocked by policy guard
            if ws_guard.is_blocked():
                block_info = ws_guard.get_block_info()
                logger.info(f"[market_ws] Connection blocked until {block_info.get('blocked_until')}")
                await asyncio.sleep(60)  # Check every minute when blocked
                continue
            
            # Record attempt and check if allowed
            if not await ws_guard.record_attempt():
                await asyncio.sleep(60)  # Wait when blocked
                continue
            
            try:
                await self._connect_and_process()
                await ws_guard.record_success()
                backoff = 1  # Reset backoff on successful connection
                
            except Exception as e:
                self.error_count += 1
                
                # Check for policy violation
                if "policy violation" in str(e).lower() or "1008" in str(e):
                    await ws_guard.handle_policy_violation(self.connection_id or "unknown")
                    backoff = 60  # Wait longer after policy violation
                else:
                    logger.warning(f"[market_ws] Connection error: {e}, reconnecting in {backoff}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                
    async def _connect_and_process(self) -> None:
        """Connect to Hyperliquid feed and process messages."""
        try:
            async with websockets.connect(
                self.ws_url, 
                ping_interval=None,  # We handle our own pings
                close_timeout=10
            ) as ws:
                self.ws = ws
                self.connected = True
                self.reconnect_count += 1
                logger.info("[market_ws] Connected to Hyperliquid feed")
                
                # Send subscription message
                await self._send_subscription(ws)
                
                # Process messages
                async for raw_message in ws:
                    if not self.running:
                        break
                        
                    try:
                        await self._handle_message(raw_message)
                        await self._check_heartbeat(ws)
                        
                    except Exception as e:
                        logger.error(f"[market_ws] Error processing message: {e}")
                        self.error_count += 1
                        
        except Exception as e:
            self.connected = False
            raise e
            
    async def _send_subscription(self, ws) -> None:
        """Send compliant subscription messages for all symbols."""
        # Subscribe to trades for each symbol
        for symbol in self.symbols:
            trades_msg = {
                "method": "subscribe",
                "subscription": {"type": "trades", "coin": symbol}
            }
            await self._send_with_rate_limit(ws, trades_msg)
            
            # Subscribe to bookTop for each symbol (prefer bookTop for stability)
            book_msg = {
                "method": "subscribe", 
                "subscription": {"type": "bookTop", "coin": symbol}
            }
            await self._send_with_rate_limit(ws, book_msg)
        
        logger.info(f"[market_ws] Subscribed to trades and bookTop for {len(self.symbols)} symbols")
        
    async def _send_with_rate_limit(self, ws, message: dict) -> None:
        """Send message with rate limiting."""
        async with RATE_LIMIT:
            await ws.send(json.dumps(message))
            await asyncio.sleep(0.05)  # 20 msg/s = 50ms between messages
            
    async def _check_heartbeat(self, ws) -> None:
        """Check if heartbeat is needed."""
        now = time.time()
        if now - self.last_ping_ts > HEARTBEAT_INTERVAL:
            await self._send_with_rate_limit(ws, "ping")
            self.last_ping_ts = now
            self.pings_sent += 1
            logger.debug(f"[market_ws] Ping sent (total: {self.pings_sent})")
    
    def _handle_ack(self, message: dict) -> None:
        """Handle subscription acknowledgments."""
        ack_data = message.get("ack", {})
        coin = ack_data.get("coin")
        channel = ack_data.get("channel")
        
        if coin and channel:
            if coin not in self.acks_received:
                self.acks_received[coin] = {}
            self.acks_received[coin][channel] = True
            logger.info(f"[market_ws] ACK received for {coin} {channel}")
            
            # Check if all subscriptions are acknowledged
            self._check_subscription_health()
    
    def _check_subscription_health(self) -> None:
        """Check if all subscriptions are properly acknowledged."""
        expected_subscriptions = len(self.symbols) * 2  # trades + bookTop for each symbol
        received_acks = sum(len(channels) for channels in self.acks_received.values())
        
        self.subscription_acks_ok = received_acks >= expected_subscriptions
        if self.subscription_acks_ok:
            logger.info(f"[market_ws] All subscriptions acknowledged ({received_acks}/{expected_subscriptions})")
            
    async def _handle_message(self, raw_message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            message = json.loads(raw_message)
            self.last_tick_ts = time.time()
            self.total_ticks += 1
            
            # Handle acknowledgments
            if isinstance(message, dict) and "ack" in message:
                self._handle_ack(message)
                return
            
            # Handle different message types
            if isinstance(message, dict):
                if "data" in message:
                    await self._handle_tick_data(message)
                elif message.get("type") == "pong":
                    logger.debug("[market_ws] Pong received")
                else:
                    logger.debug(f"[market_ws] Unknown message type: {message}")
            else:
                logger.debug(f"[market_ws] Non-dict message: {message}")
                
        except json.JSONDecodeError as e:
            logger.error(f"[market_ws] JSON decode error: {e}")
            self.error_count += 1
            
    async def _handle_tick_data(self, message: dict) -> None:
        """Handle tick data and update cache."""
        data = message.get("data", {})
        symbol = data.get("coin")
        
        if not symbol or symbol not in self.symbols:
            return
            
        # Extract tick data
        mid = data.get("mid")
        spread_bps = data.get("spread_bps")
        obi = data.get("obi")
        
        if mid is not None:
            # Update cache
            update_tick(symbol, mid=mid, spread_bps=spread_bps, obi=obi)
            self.symbols_active.add(symbol)
            
            # Log structured tick
            logger.info(f"[market_ws] {symbol} mid={mid} spread={spread_bps}bps obi={obi}")
            
    def get_cached(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached market data for symbol (non-blocking)."""
        from backend.services.market_cache import get_cached as get_cache
        cached_tick = get_cache(symbol)
        if not cached_tick:
            return None
        return {
            "mid": cached_tick.mid,
            "spread_bps": cached_tick.spread_bps,
            "obi": cached_tick.obi,
            "last_tick_ts": cached_tick.last_tick_ts
        }
    
    def last_tick_s_ago(self) -> float:
        """Get seconds since last tick."""
        if self.last_tick_ts == 0:
            return 999.0
        return time.time() - self.last_tick_ts
    
    def get_reconnect_count(self) -> int:
        """Get total reconnection count."""
        return self.reconnect_count
    
    def is_connected(self) -> bool:
        """Check if feed is connected."""
        return self.connected and self.last_tick_s_ago() < 3.0
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get WebSocket health metrics."""
        now = time.time()
        last_tick_s_ago = now - self.last_tick_ts if self.last_tick_ts > 0 else 999
        
        return {
            "connected": self.connected,
            "last_tick_s_ago": round(last_tick_s_ago, 1),
            "symbols_active": len(self.symbols_active),
            "reconnects": self.reconnect_count,
            "total_ticks": self.total_ticks,
            "error_count": self.error_count,
            "pings_sent": self.pings_sent,
            "symbols": list(self.symbols_active)
        }

# Global client instance
_ws_client: Optional[HyperliquidWSClient] = None

async def start_hyperliquid_ws(symbols: List[str]) -> None:
    """Start the global Hyperliquid WebSocket client."""
    global _ws_client
    
    if _ws_client is not None:
        await _ws_client.stop()
        
    _ws_client = HyperliquidWSClient(symbols)
    await _ws_client.start()

async def stop_hyperliquid_ws() -> None:
    """Stop the global Hyperliquid WebSocket client."""
    global _ws_client
    
    if _ws_client is not None:
        await _ws_client.stop()
        _ws_client = None

def get_hyperliquid_ws() -> Optional[HyperliquidWSClient]:
    """Get the global WebSocket client."""
    return _ws_client
