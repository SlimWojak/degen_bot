"""
AI Trading Routes - Manual controls and kill switch
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import settings
from common.hl_client import connect, place_ioc_limit_adaptive, discover_price, usd_to_size
import sqlite3

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory kill switch state
_kill_switch_enabled = True

class OrderRequest(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    notional_usd: float
    reduce_only: bool = False

class KillSwitchRequest(BaseModel):
    enabled: bool

def log_trade_to_sqlite(symbol: str, side: str, notional_usd: float, avg_px: float, order_id: str, status: str):
    """Log trade to SQLite database"""
    try:
        conn = sqlite3.connect("data/trades.db")
        cursor = conn.cursor()
        
        # Create trades table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                side TEXT,
                notional_usd REAL,
                avg_px REAL,
                order_id TEXT,
                status TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert trade record
        cursor.execute("""
            INSERT INTO trades (symbol, side, notional_usd, avg_px, order_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, side, notional_usd, avg_px, order_id, status))
        
        conn.commit()
        conn.close()
        logger.info(f"Trade logged to SQLite: {symbol} {side} ${notional_usd} @ ${avg_px}")
    except Exception as e:
        logger.error(f"Failed to log trade to SQLite: {e}")

@router.post("/order/limit_ioc")
async def place_limit_ioc_order(request: Request, order: OrderRequest):
    """Place a limit IOC order with validation and caps"""
    request_id = str(uuid.uuid4())
    
    # Structured logging
    logger.info(f"AI_ORDER_REQUEST: {{'request_id': '{request_id}', 'symbol': '{order.symbol}', 'side': '{order.side}', 'notional_usd': {order.notional_usd}, 'reduce_only': {order.reduce_only}, 'client_ip': '{request.client.host if request.client else 'unknown'}'}}")
    
    try:
        # Check kill switch
        if not _kill_switch_enabled:
            logger.warning(f"AI_ORDER_REJECTED: {{'request_id': '{request_id}', 'reason': 'kill_switch_disabled'}}")
            raise HTTPException(status_code=403, detail={"error": "kill switch disabled"})
        
        # Check trading enabled
        if not settings.HL_TRADING_ENABLED:
            logger.warning(f"AI_ORDER_REJECTED: {{'request_id': '{request_id}', 'reason': 'trading_disabled'}}")
            raise HTTPException(status_code=403, detail={"error": "trading disabled"})
        
        # Validate notional amount
        if order.notional_usd > settings.HL_MAX_NOTIONAL_USD:
            logger.warning(f"AI_ORDER_REJECTED: {{'request_id': '{request_id}', 'reason': 'notional_exceeds_cap', 'requested': {order.notional_usd}, 'max_allowed': {settings.HL_MAX_NOTIONAL_USD}}}")
            raise HTTPException(status_code=400, detail={"error": f"notional ${order.notional_usd} exceeds cap of ${settings.HL_MAX_NOTIONAL_USD}"})
        
        # Validate side
        if order.side.lower() not in ["buy", "sell"]:
            logger.warning(f"AI_ORDER_REJECTED: {{'request_id': '{request_id}', 'reason': 'invalid_side', 'side': '{order.side}'}}")
            raise HTTPException(status_code=400, detail={"error": "side must be 'buy' or 'sell'"})
        
        # Execute order using hl_client
        if settings.DATA_SOURCE == "live":
            try:
                exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
                
                # Discover current price
                current_price = discover_price(info, order.symbol)
                if not current_price:
                    raise HTTPException(status_code=400, detail={"error": f"could not discover price for {order.symbol}"})
                
                # Calculate size
                size = usd_to_size(info, order.symbol, order.notional_usd)
                
                # Calculate crossed price (1% aggressive for IOC)
                crossed_price = current_price * (1.01 if order.side.lower() == "buy" else 0.99)
                
                # Place order
                result = place_ioc_limit_adaptive(
                    exchange, info, order.symbol, 
                    is_buy=(order.side.lower() == "buy"),
                    size=size,
                    crossed_px=crossed_price,
                    reduce_only=order.reduce_only
                )
                
                # Extract order details
                if result.get("result") and result["result"].get("response"):
                    response_data = result["result"]["response"]
                    if isinstance(response_data, dict) and "data" in response_data:
                        order_data = response_data["data"]
                        if isinstance(order_data, dict) and "statuses" in order_data:
                            statuses = order_data["statuses"]
                            if statuses and len(statuses) > 0:
                                status = statuses[0]
                                if isinstance(status, dict):
                                    order_id = status.get("resting", {}).get("oid", "unknown")
                                    avg_px = status.get("resting", {}).get("avgPx", 0.0)
                                    
                                    # Log to SQLite
                                    log_trade_to_sqlite(
                                        order.symbol, order.side, order.notional_usd, 
                                        avg_px, order_id, "filled"
                                    )
                                    
                                    logger.info(f"AI_ORDER_SUCCESS: {{'request_id': '{request_id}', 'order_id': '{order_id}', 'avg_px': {avg_px}, 'symbol': '{order.symbol}', 'side': '{order.side}', 'notional_usd': {order.notional_usd}}}")
                                    
                                    return {
                                        "status": "success",
                                        "order_id": order_id,
                                        "avg_px": avg_px,
                                        "symbol": order.symbol,
                                        "side": order.side,
                                        "notional_usd": order.notional_usd,
                                        "request_id": request_id
                                    }
                
                # If we get here, order didn't fill properly
                logger.warning(f"AI_ORDER_PARTIAL: {{'request_id': '{request_id}', 'reason': 'order_not_filled', 'result': {result}}}")
                return {
                    "status": "partial",
                    "message": "Order placed but may not have filled",
                    "request_id": request_id
                }
                
            except Exception as e:
                logger.error(f"AI_ORDER_ERROR: {{'request_id': '{request_id}', 'error': '{str(e)}', 'type': '{type(e).__name__}'}}")
                raise HTTPException(status_code=500, detail={"error": f"order execution failed: {str(e)}"})
        else:
            # Mock mode - simulate successful order
            mock_order_id = f"mock_{request_id[:8]}"
            mock_avg_px = 2000.0 if order.symbol == "ETH" else 100.0
            
            # Log to SQLite even in mock mode
            log_trade_to_sqlite(
                order.symbol, order.side, order.notional_usd, 
                mock_avg_px, mock_order_id, "mock_filled"
            )
            
            logger.info(f"AI_ORDER_MOCK_SUCCESS: {{'request_id': '{request_id}', 'order_id': '{mock_order_id}', 'avg_px': {mock_avg_px}, 'symbol': '{order.symbol}', 'side': '{order.side}', 'notional_usd': {order.notional_usd}}}")
            
            return {
                "status": "success",
                "order_id": mock_order_id,
                "avg_px": mock_avg_px,
                "symbol": order.symbol,
                "side": order.side,
                "notional_usd": order.notional_usd,
                "request_id": request_id,
                "mock": True
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI_ORDER_ERROR: {{'request_id': '{request_id}', 'error': '{str(e)}', 'type': '{type(e).__name__}'}}")
        raise HTTPException(status_code=500, detail={"error": f"unexpected error: {str(e)}"})

@router.get("/kill_switch")
async def get_kill_switch():
    """Get current kill switch state"""
    return {"enabled": _kill_switch_enabled}

@router.post("/kill_switch")
async def set_kill_switch(kill_switch: KillSwitchRequest):
    """Set kill switch state"""
    global _kill_switch_enabled
    old_state = _kill_switch_enabled
    _kill_switch_enabled = kill_switch.enabled
    
    logger.info(f"KILL_SWITCH_CHANGED: {{'old_state': {old_state}, 'new_state': {_kill_switch_enabled}, 'timestamp': '{datetime.now().isoformat()}'}}")
    
    return {"enabled": _kill_switch_enabled}
