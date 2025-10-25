"""
HL Routes - Hyperliquid trading endpoints using hl_client.py
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import re
import logging
from eth_account import Account
from backend.config import settings
from common.hl_client import (
    connect, base_url_for, discover_price, usd_to_size, ioc_round_trip
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/preflight")
def hl_preflight():
    """HL preflight check - sanity + visibility"""
    # Mask key in logs; return structured diagnostics
    try:
        network = settings.HL_NETWORK
        base_url = base_url_for(network)
        signer_pk = settings.HL_PRIVATE_KEY
        if not signer_pk or not settings.HL_ACCOUNT_ADDRESS:
            raise HTTPException(status_code=400, detail="Missing HL_ACCOUNT_ADDRESS or HL_PRIVATE_KEY")

        # Signer address from private key
        signer_addr = Account.from_key(signer_pk).address

        # derive signer and expose a safe fingerprint for debug
        raw_pk = settings.HL_PRIVATE_KEY
        
        def fp(s: str, n: int = 6) -> str:
            return f"{s[:n]}...{s[-n:]}" if s and len(s) > 2*n else s

        env_view = {
            "HL_NETWORK": settings.HL_NETWORK,
            "HL_SYMBOL": settings.HL_SYMBOL,
            "HL_PRIVATE_KEY_len": len(raw_pk) if raw_pk else 0,
            "HL_PRIVATE_KEY_fp": fp(raw_pk),
        }
        
        print(f"[DEBUG] env_view: {env_view}")  # Debug logging

        exch, info = connect(network, signer_pk)
        px = discover_price(info, settings.HL_SYMBOL)
        size_15 = usd_to_size(info, settings.HL_SYMBOL, 15.0)

        result = {
            "network": network,
            "base_url": base_url,
            "owner_addr": settings.HL_ACCOUNT_ADDRESS,
            "signer_addr": signer_addr,
            "symbol": settings.HL_SYMBOL,
            "price_sample": px,
            "size_from_15_usd": size_15,
            "sdk_order_signature": "order(name, is_buy, sz, limit_px, order_type, reduce_only=False, cloid=None, builder=None)",
            "env_debug": env_view,
        }
        
        # Structured JSON log for monitoring
        logger.info(f"HL_PREFLIGHT_SUCCESS: {{'network': '{network}', 'signer_addr': '{signer_addr}', 'symbol': '{settings.HL_SYMBOL}', 'price_sample': {px}, 'signer_impl': '{settings.HL_SIGNER_IMPL}'}}")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ioc_roundtrip")
def hl_ioc_roundtrip(
    notional_usd: Optional[float] = Query(None, description="USD notional amount"),
    hold_seconds: Optional[int] = Query(None, description="Hold time in seconds"),
    side: str = Query("buy", description="Trade side: buy or sell"),
    symbol: Optional[str] = Query(None, description="Trading symbol")
):
    """Execute IOC round-trip trade with configurable parameters"""
    try:
        network = settings.HL_NETWORK
        signer = settings.HL_PRIVATE_KEY
        if not signer or not settings.HL_ACCOUNT_ADDRESS:
            raise HTTPException(status_code=400, detail="Missing HL_ACCOUNT_ADDRESS or HL_PRIVATE_KEY")

        exch, info = connect(network, signer)
        sym = (symbol or settings.HL_SYMBOL).upper()
        usd = float(notional_usd or settings.HL_NOTIONAL_USD)
        hold = int(hold_seconds or settings.HL_EXIT_AFTER_SECONDS)

        result = ioc_round_trip(exch, info, sym, usd, hold, side=side)
        # Optionally compress the response for UI
        return {
            "symbol": sym,
            "notional_usd": usd,
            "hold_seconds": hold,
            "side": side,
            "entry": result.get("entry"),
            "exit": result.get("exit"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
