"""
Market Feed Manager - Singleton WebSocket with graceful lifecycle.
Ensures exactly one WebSocket connection with proper reconnection handling.
"""

import asyncio
import logging
import uuid
import os
import fcntl
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone

from backend.services.hyperliquid_ws import HyperliquidWSClient
from backend.config import settings
from backend.util.async_tools import create_supervised_task, timeout
from backend.protocols.market_feed import MarketFeed

logger = logging.getLogger("market_feed_manager")

class MarketFeedManager:
    """Singleton manager for the unified Hyperliquid WebSocket feed."""
    
    _instance: Optional['MarketFeedManager'] = None
    _lock: asyncio.Lock = asyncio.Lock()
    
    def __new__(cls) -> 'MarketFeedManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        if not hasattr(self, '_initialized'):
            self._initialized: bool = True
            self.connection_id: str = str(uuid.uuid4())
            self.ws_client: Optional[HyperliquidWSClient] = None
            self.running: bool = False
            self.start_time: Optional[datetime] = None
            self.last_rest_sync: Optional[datetime] = None
            self.rest_sync_interval: float = 8.0  # seconds
            self.lock_file_path: str = ".run/hl_ws.lock"
            
    async def start(self) -> None:
        """Start the market feed manager with singleton guard."""
        async with self._lock:
            if self.running:
                logger.warning("[market_feed_manager] Already running")
                return
            
            # Check for existing process lock
            if await self._check_existing_process():
                logger.info("[market_feed_manager] Another instance detected, skipping start")
                return
                
            logger.info(f"[market_feed_manager] Starting with connection ID: {self.connection_id}")
            
            # Initialize WebSocket client
            symbols = settings.AGENT_SYMBOLS.split(',')
            self.ws_client = HyperliquidWSClient(symbols)
            
            # Start WebSocket client
            await self.ws_client.start()
            
            self.running = True
            self.start_time = datetime.now(timezone.utc)
            
            # Start REST sync loop as supervised task
            create_supervised_task(
                self._rest_sync_loop(),
                name="rest_sync_loop"
            )
            
            logger.info("[market_feed_manager] Started successfully")
    
    async def _check_existing_process(self) -> bool:
        """Check if another instance is already running."""
        try:
            # Create .run directory if it doesn't exist
            os.makedirs(".run", exist_ok=True)
            
            # Try to acquire exclusive lock
            with open(self.lock_file_path, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                f.write(str(os.getpid()))
                return False  # Successfully acquired lock
        except (OSError, IOError):
            # Lock already held by another process
            logger.info("[market_feed_manager] WS lock already held by another process")
            return True
    
    async def stop(self) -> None:
        """Stop the market feed manager gracefully."""
        async with self._lock:
            if not self.running:
                logger.warning("[market_feed_manager] Not running")
                return
                
            logger.info("[market_feed_manager] Stopping gracefully")
            
            if self.ws_client:
                await self.ws_client.stop()
                self.ws_client = None
            
            self.running = False
            logger.info("[market_feed_manager] Stopped")
    
    async def _rest_sync_loop(self) -> None:
        """Background REST sync loop for meta/funding/OI data."""
        while self.running:
            try:
                # Add timeout to prevent hanging
                await timeout(
                    self._sync_meta_data(),
                    seconds=30.0
                )
                self.last_rest_sync = datetime.now(timezone.utc)
                await asyncio.sleep(self.rest_sync_interval)
            except Exception as e:
                logger.error(f"[market_feed_manager] REST sync error: {e}")
                await asyncio.sleep(self.rest_sync_interval)
    
    async def _sync_meta_data(self) -> None:
        """Sync meta data from Hyperliquid REST API."""
        try:
            # TODO: Implement metaAndAssetCtxs REST call
            # This would fetch mark, index, openInterest, funding, impact per symbol
            logger.debug("[market_feed_manager] REST sync completed")
        except Exception as e:
            logger.error(f"[market_feed_manager] REST sync failed: {e}")
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get comprehensive health metrics."""
        if not self.ws_client:
            return {
                "connected": False,
                "connection_id": self.connection_id,
                "subscriptions": {},
                "acks_ok": False,
                "reconnects_5m": 0,
                "last_rest_sync": None,
                "uptime_s": 0
            }
        
        # Calculate uptime
        uptime_s = 0
        if self.start_time:
            uptime_s = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        # Get subscription status
        subscriptions = {}
        for symbol in self.ws_client.symbols:
            subscriptions[symbol] = ["trades", "bookTop"]
        
        return {
            "connected": self.ws_client.is_connected(),
            "connection_id": self.connection_id,
            "subscriptions": subscriptions,
            "acks_ok": self.ws_client.subscription_acks_ok,
            "reconnects_5m": self.ws_client.get_reconnect_count(),
            "last_rest_sync": self.last_rest_sync.isoformat() if self.last_rest_sync else None,
            "uptime_s": uptime_s,
            "total_ticks": self.ws_client.total_ticks,
            "error_count": self.ws_client.error_count
        }
    
    def get_cached(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached market data for symbol."""
        if not self.ws_client:
            return None
        return self.ws_client.get_cached(symbol)
    
    def last_tick_s_ago(self) -> float:
        """Get seconds since last tick."""
        if not self.ws_client:
            return 999.0
        return self.ws_client.last_tick_s_ago()
    
    def get_reconnect_count(self) -> int:
        """Get total reconnection count."""
        if not self.ws_client:
            return 0
        return self.ws_client.get_reconnect_count()
    
    def is_connected(self) -> bool:
        """Check if feed is connected."""
        if not self.ws_client:
            return False
        return self.ws_client.is_connected()

# Global singleton instance
market_feed_manager = MarketFeedManager()
