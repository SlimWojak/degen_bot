"""
hl_client.py — Canonical Hyperliquid client for DEGEN_BOT.

This wraps the verified sandbox logic:
- SDK v0.20.0 constructors (Exchange(wallet=LocalAccount, base_url=...))
- Price discovery (l2_snapshot -> all_mids)
- Precision helpers (pxDecimals/szDecimals)
- Adaptive tick snapping (x1,x2,x5,x10,x20,x25,x50; floor/ceil/round)
- Limit IOC entry/exit (exit reduce_only=True)
"""

import os
import time
import asyncio
from typing import Any, Dict, Tuple, Optional, List

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

# -----------------------
# Base URL / Connect
# -----------------------

def base_url_for(network: str) -> str:
    n = (network or "testnet").strip().lower()
    if n == "mainnet":
        return "https://api.hyperliquid.xyz"
    return "https://api.hyperliquid-testnet.xyz"

def connect(network: str, api_private_key_hex: str) -> Tuple[Exchange, Info]:
    """Build SDK clients using the API wallet private key (signer)."""
    wallet = Account.from_key(api_private_key_hex)
    url = base_url_for(network)
    info = Info(base_url=url)
    exch = Exchange(wallet=wallet, base_url=url)
    return exch, info

# -----------------------
# Precision helpers
# -----------------------

def _meta_universe(info: Info) -> List[Dict[str, Any]]:
    try:
        m = info.meta()
        return m.get("universe", []) or []
    except Exception:
        return []

def px_decimals_for_symbol(info: Info, symbol: str) -> int:
    for c in _meta_universe(info):
        if c.get("name") == symbol:
            return int(c.get("pxDecimals", 2))
    return 2

def sz_decimals_for_symbol(info: Info, symbol: str) -> int:
    for c in _meta_universe(info):
        if c.get("name") == symbol:
            return int(c.get("szDecimals", 3))
    return 3

def quantize_px(info: Info, symbol: str, px: float) -> float:
    return round(float(px), px_decimals_for_symbol(info, symbol))

def quantize_size(info: Info, symbol: str, size: float) -> float:
    return round(float(size), sz_decimals_for_symbol(info, symbol))

def tick_size_for_symbol(info: Info, symbol: str) -> float:
    dec = px_decimals_for_symbol(info, symbol)
    return 10 ** (-dec)

def snap_to_tick(px: float, tick: float, mode: str = "round") -> float:
    if px is None or tick <= 0:
        return px
    q = px / tick
    if mode == "floor":
        q = int(q)
    elif mode == "ceil":
        q = int(q + 0.9999999)
    else:
        q = round(q)
    return q * tick

def tick_candidates(info: Info, symbol: str) -> List[float]:
    base = tick_size_for_symbol(info, symbol)
    return [base * k for k in (1, 2, 5, 10, 20, 25, 50)]

# -----------------------
# Price discovery
# -----------------------

def price_from_l2(info: Info, symbol: str) -> Optional[float]:
    if hasattr(info, "l2_snapshot"):
        try:
            s = info.l2_snapshot(symbol)
            bids = (s.get("levels", {}) or {}).get("bid", [])
            asks = (s.get("levels", {}) or {}).get("ask", [])
            bid = float(bids[0][0]) if bids else None
            ask = float(asks[0][0]) if asks else None
            if bid and ask: return (bid + ask) / 2.0
            return bid or ask
        except Exception:
            return None
    return None

def price_from_all_mids(info: Info, symbol: str) -> Optional[float]:
    if hasattr(info, "all_mids"):
        try:
            mids = info.all_mids()
            if isinstance(mids, dict):
                v = mids.get(symbol)
                return float(v) if v is not None else None
            if isinstance(mids, list):
                for row in mids:
                    if isinstance(row, (list, tuple)) and len(row) >= 2 and row[0] == symbol:
                        return float(row[1])
        except Exception:
            return None
    return None

def discover_price(info: Info, symbol: str) -> Optional[float]:
    for fn in (price_from_l2, price_from_all_mids):
        px = fn(info, symbol)
        if px and px > 0:
            return px
    return None

# -----------------------
# Order helpers (SDK 0.20.0 signature)
# -----------------------

async def _send_limit_ioc(exchange: Exchange, symbol: str, is_buy: bool, sz: float, limit_px: float, reduce_only: bool):
    """Send limit IOC order with rate limiting."""
    # Import here to avoid circular imports
    try:
        from backend.util.ratelimit import get_order_limiter
        await get_order_limiter().acquire()
    except ImportError:
        # Fallback if rate limiter not available
        pass
    
    order_type = {"limit": {"tif": "Ioc"}}
    kwargs = dict(
        name=symbol,
        is_buy=is_buy,
        sz=sz,
        limit_px=limit_px,
        order_type=order_type,
        reduce_only=reduce_only,
    )
    resp = exchange.order(**kwargs)
    return {"request": kwargs, "response": resp}

def _is_tick_error(statuses) -> bool:
    try:
        if not statuses:
            return False
        for s in statuses or []:
            if isinstance(s, dict):
                msg = s.get("error") or ""
                if "divisible by tick size" in msg:
                    return True
    except Exception:
        pass
    return False

def place_ioc_limit_adaptive(exchange: Exchange, info: Info, symbol: str, is_buy: bool, size: float, crossed_px: float, reduce_only: bool = False) -> Dict[str, Any]:
    sz_q = quantize_size(info, symbol, size)
    attempts = []
    for tick in tick_candidates(info, symbol):
        for mode in ("round", "floor", "ceil"):
            px_snapped = snap_to_tick(crossed_px, tick, mode)
            px_q = quantize_px(info, symbol, px_snapped)
            out = _send_limit_ioc(exchange, symbol, is_buy, sz_q, px_q, reduce_only)
            attempts.append(out)
            
            # Handle different response structures safely
            statuses = None
            try:
                response = out.get("response", {})
                if isinstance(response, dict):
                    response_data = response.get("response", {})
                    if isinstance(response_data, dict):
                        data = response_data.get("data", {})
                        if isinstance(data, dict):
                            statuses = data.get("statuses")
            except Exception:
                pass
                
            if not _is_tick_error(statuses):
                return {"attempts": attempts, "chosen_tick": tick, "mode": mode, "result": out}
    return {"attempts": attempts, "error": "all tick candidates failed"}

# -----------------------
# Public convenience APIs
# -----------------------

def usd_to_size(info: Info, symbol: str, usd: float) -> float:
    px = discover_price(info, symbol)
    if not px:
        # fallback tiny size (still quantized)
        return quantize_size(info, symbol, 0.001)
    return quantize_size(info, symbol, float(usd) / float(px))

def ioc_round_trip(ex: Exchange, info: Info, symbol: str, notional_usd: float, hold_seconds: int = 5, side: str = "buy") -> Dict[str, Any]:
    """
    Place entry IOC ~notional_usd, wait hold_seconds, exit IOC reduce_only on the opposite side.
    Returns dict with entry/exit attempts and results.
    """
    is_buy = (side.lower() == "buy")
    px = discover_price(info, symbol)
    if not px:
        raise RuntimeError(f"Cannot discover price for {symbol}")
    size = usd_to_size(info, symbol, notional_usd)

    # cross ~1% for IOC
    crossed_entry = px * (1.0 + 0.01) if is_buy else px * (1.0 - 0.01)
    entry = place_ioc_limit_adaptive(ex, info, symbol, is_buy=is_buy, size=size, crossed_px=crossed_entry, reduce_only=False)

    time.sleep(max(1, int(hold_seconds)))

    crossed_exit = px * (1.0 + 0.01) if (not is_buy) else px * (1.0 - 0.01)
    exit_res = place_ioc_limit_adaptive(ex, info, symbol, is_buy=(not is_buy), size=size, crossed_px=crossed_exit, reduce_only=True)

    return {"entry": entry, "exit": exit_res}
