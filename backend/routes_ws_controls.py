"""
WebSocket control endpoints for admin/dev operations.
Provides manual control over WS blocking and unblocking.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from backend.services.ws_guard import ws_guard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops/controls", tags=["ws-controls"])

@router.post("/unblock")
async def unblock_ws() -> Dict[str, Any]:
    """
    Manually unblock WebSocket connections (dev/admin only).
    Clears the policy violation block to allow reconnection attempts.
    """
    try:
        await ws_guard.manual_unblock()
        
        logger.info("WS block manually cleared via /ops/controls/unblock")
        
        return {
            "success": True,
            "message": "WebSocket block cleared",
            "timestamp": ws_guard.get_block_info()
        }
        
    except Exception as e:
        logger.error(f"Failed to unblock WS: {e}")
        raise HTTPException(status_code=500, detail=f"Unblock failed: {str(e)}")

@router.post("/ws-stop")
async def stop_ws(minutes: int = 30) -> Dict[str, Any]:
    """
    Force stop WebSocket and block for specified minutes (safety lever).
    
    Args:
        minutes: Number of minutes to block (default: 30, max: 120)
    """
    try:
        # Limit to reasonable range
        minutes = max(1, min(minutes, 120))
        
        await ws_guard.force_block(minutes)
        
        logger.warning(f"WS manually blocked for {minutes} minutes via /ops/controls/ws-stop")
        
        return {
            "success": True,
            "message": f"WebSocket blocked for {minutes} minutes",
            "blocked_until": ws_guard.get_block_info().get("blocked_until"),
            "minutes": minutes
        }
        
    except Exception as e:
        logger.error(f"Failed to block WS: {e}")
        raise HTTPException(status_code=500, detail=f"Block failed: {str(e)}")

@router.get("/ws-status")
async def ws_status() -> Dict[str, Any]:
    """Get detailed WebSocket status and guard information."""
    try:
        stats = ws_guard.get_stats()
        block_info = ws_guard.get_block_info()
        
        return {
            "guard_stats": stats,
            "block_info": block_info,
            "is_blocked": ws_guard.is_blocked(),
            "timestamp": ws_guard.get_block_info()
        }
        
    except Exception as e:
        logger.error(f"Failed to get WS status: {e}")
        raise HTTPException(status_code=500, detail=f"Status failed: {str(e)}")
