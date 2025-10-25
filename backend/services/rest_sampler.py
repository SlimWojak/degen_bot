"""
REST-backed degraded mode sampler.
Provides market data via REST API when WebSocket is blocked.
"""

import asyncio
import logging
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("rest_sampler")

class RESTSampler:
    """REST API sampler for degraded mode operation."""
    
    def __init__(self):
        self.running = False
        self.last_meta_sync: Optional[datetime] = None
        self.meta_data: Dict[str, Any] = {}
        self.sync_interval = 8.0  # seconds
        self.client: Optional[httpx.AsyncClient] = None
        
    async def start(self) -> None:
        """Start the REST sampler."""
        if self.running:
            return
            
        self.running = True
        self.client = httpx.AsyncClient(timeout=10.0)
        asyncio.create_task(self._sync_loop())
        logger.info("[rest_sampler] Started REST sampler")
    
    async def stop(self) -> None:
        """Stop the REST sampler."""
        self.running = False
        if self.client:
            await self.client.aclose()
        logger.info("[rest_sampler] Stopped REST sampler")
    
    async def _sync_loop(self) -> None:
        """Background sync loop for meta data."""
        while self.running:
            try:
                await self._sync_meta_data()
                self.last_meta_sync = datetime.now(timezone.utc)
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"[rest_sampler] Sync error: {e}")
                await asyncio.sleep(self.sync_interval)
    
    async def _sync_meta_data(self) -> None:
        """Sync meta data from Hyperliquid REST API."""
        if not self.client:
            return
            
        try:
            # Call metaAndAssetCtxs endpoint
            response = await self.client.get("https://api.hyperliquid.xyz/info", 
                                           params={"type": "metaAndAssetCtxs"})
            response.raise_for_status()
            
            data = response.json()
            self.meta_data = data
            
            logger.debug("[rest_sampler] Meta data synced successfully")
            
        except Exception as e:
            logger.error(f"[rest_sampler] Failed to sync meta data: {e}")
    
    def get_health_info(self) -> Dict[str, Any]:
        """Get REST sampler health information."""
        return {
            "rest_meta_ok": self.last_meta_sync is not None,
            "last_meta_sync": self.last_meta_sync.isoformat() if self.last_meta_sync else None,
            "meta_data_keys": list(self.meta_data.keys()) if self.meta_data else [],
            "sync_interval": self.sync_interval
        }
    
    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get market data for symbol from REST meta data."""
        if not self.meta_data or "assetContexts" not in self.meta_data:
            return {}
        
        # Find asset context for symbol
        for asset in self.meta_data.get("assetContexts", []):
            if asset.get("symbol") == symbol:
                return {
                    "mark_px": asset.get("markPx"),
                    "index_px": asset.get("indexPx"),
                    "open_interest": asset.get("openInterest"),
                    "funding": asset.get("funding"),
                    "impact_pxs": asset.get("impactPxs", []),
                    "source": "rest",
                    "last_update": self.last_meta_sync.isoformat() if self.last_meta_sync else None
                }
        
        return {}

# Global REST sampler instance
rest_sampler = RESTSampler()
