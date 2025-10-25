"""
Hyperliquid signing utilities for deterministic serialization and canonical formatting.
"""
from decimal import Decimal, ROUND_DOWN
import json
from typing import Union
from collections import OrderedDict
from collections.abc import Mapping, Sequence


def to_plain(obj):
    """Deep-convert any lingering OrderedDict to plain dict before msgpack."""
    if isinstance(obj, OrderedDict):
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, Mapping):
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_plain(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(to_plain(v) for v in obj)
    return obj

def canon_addr(addr: str) -> str:
    """Ensure address is lowercase hex with 0x prefix. Only call on real addresses."""
    if not isinstance(addr, str):
        return addr  # Don't touch non-strings
    if not addr.startswith('0x'):
        addr = '0x' + addr
    return addr.lower()


def canon_json(obj: dict) -> str:
    """Create canonical JSON string with sorted keys and no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def to_decimal_str(x: Union[float, str, Decimal], places: int) -> str:
    """
    Convert to decimal string with exact number of decimal places.
    Uses ROUND_DOWN for safety in trading contexts.
    """
    if isinstance(x, str):
        x = Decimal(x)
    elif isinstance(x, float):
        x = Decimal(str(x))
    elif not isinstance(x, Decimal):
        x = Decimal(str(x))
    
    q = Decimal(10) ** -places
    return str(x.quantize(q, rounding=ROUND_DOWN))


def to_wire_decimal(x: float) -> str:
    """Trim numeric strings before building the action"""
    s = f"{x:.18f}".rstrip('0').rstrip('.')
    return s if s != "" else "0"

def build_order_short(asset: int, is_buy: bool, px_str: str, sz_str: str, reduce_only: bool, tif: str = "Ioc"):
    """
    Build order with strict field order using OrderedDict.
    px_str should already be "0" for IOC market; sz_str must be trimmed (no trailing zeros)
    """
    from collections import OrderedDict
    
    order = OrderedDict()
    order["a"] = asset
    order["b"] = is_buy
    order["p"] = px_str
    order["s"] = sz_str
    order["r"] = reduce_only
    order["t"] = {"limit": {"tif": tif}}
    return order

def build_action_short(order):
    """Build action with strict field order using OrderedDict"""
    from collections import OrderedDict
    
    action = OrderedDict()
    action["type"] = "order"
    action["orders"] = [order]
    action["grouping"] = "na"
    return action

def build_short_action(asset_id: int, is_buy: bool, sz_str: str, px_str: Union[str, None],
                       tif: str = "Ioc", reduce_only: bool = False, grouping: str = "na") -> dict:
    """
    Build short-form action using strict field order with OrderedDict.
    This ensures byte-for-byte compatibility with SDK expectations.
    """
    # Trim numeric strings
    sz_trimmed = to_wire_decimal(float(sz_str)) if '.' in sz_str else sz_str
    px_trimmed = "0" if px_str is None else (to_wire_decimal(float(px_str)) if px_str != "0" else "0")
    
    # Build with strict field order
    order = build_order_short(
        asset=int(asset_id),
        is_buy=bool(is_buy),
        px_str=px_trimmed,
        sz_str=sz_trimmed,
        reduce_only=bool(reduce_only),
        tif=tif
    )
    
    action = build_action_short(order)
    print(f"[DEBUG] build_short_action result: {action}")  # Debug logging
    return action

def create_signing_payload(action: dict, nonce: int) -> str:
    """
    Create the exact payload string that should be signed.
    This matches what Hyperliquid expects for signature verification.
    """
    payload = {
        "action": action,
        "nonce": nonce
    }
    return canon_json(payload)
