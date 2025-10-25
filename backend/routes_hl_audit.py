"""
HL Compliance Audit endpoints.
Provides comprehensive health checks for WebSocket and REST compliance.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
from datetime import datetime, timezone

from backend.services.market_feed_manager import market_feed_manager
from backend.services.market_sampler import get_data_health_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["hl-audit"])

@router.get("/hl-audit")
async def hl_audit() -> Dict[str, Any]:
    """
    Comprehensive HL compliance audit.
    
    Returns:
        WebSocket health, REST sync status, and data quality metrics.
    """
    try:
        # Get WebSocket health from manager
        ws_health = market_feed_manager.get_health_metrics()
        
        # Get data health from sampler
        data_health = get_data_health_info()
        
        # Get REST sync status
        rest_health = {
            "meta_refresh_ms": 8000,  # 8 second interval
            "last_ok": market_feed_manager.last_rest_sync.isoformat() if market_feed_manager.last_rest_sync else None
        }
        
        # Determine overall health status
        ws_healthy = (
            ws_health["connected"] and 
            ws_health["acks_ok"] and 
            ws_health["reconnects_5m"] <= 2
        )
        
        data_healthy = all(
            pct >= 0.95 for pct in data_health.get("mids_nonnull_pct", {}).values()
        )
        
        overall_healthy = ws_healthy and data_healthy
        
        return {
            "ws": {
                "connected": ws_health["connected"],
                "subscriptions": ws_health["subscriptions"],
                "acks_ok": ws_health["acks_ok"],
                "reconnects_5m": ws_health["reconnects_5m"],
                "connection_id": ws_health["connection_id"],
                "uptime_s": ws_health["uptime_s"]
            },
            "rest": rest_health,
            "data": {
                "mids_nonnull_pct": data_health.get("mids_nonnull_pct", {}),
                "status": data_health.get("status", "unknown")
            },
            "overall_healthy": overall_healthy,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"HL audit failed: {e}")
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

@router.get("/ws")
async def ws_status() -> Dict[str, Any]:
    """Get WebSocket connection status and subscription details."""
    try:
        return market_feed_manager.get_health_metrics()
    except Exception as e:
        logger.error(f"WS status failed: {e}")
        raise HTTPException(status_code=500, detail=f"WS status failed: {str(e)}")
