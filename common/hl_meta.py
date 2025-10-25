import httpx
import time

_ASSET_CACHE = {}
_ASSET_TTL = 300

async def get_asset_id(symbol: str, base_url: str) -> int:
    """Get asset ID for a symbol from Hyperliquid meta."""
    symbol = symbol.upper()
    now = time.time()
    
    # Check cache
    if _ASSET_CACHE.get("ts", 0) + _ASSET_TTL < now:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{base_url}/info", json={"type": "meta"})
            r.raise_for_status()
            _ASSET_CACHE["meta"] = r.json()
            _ASSET_CACHE["ts"] = now
    
    meta = _ASSET_CACHE["meta"]
    # Perp IDs are the index in meta["universe"] (array of coins)
    universe = meta.get("universe", [])
    idx = next((i for i, c in enumerate(universe) if c.get("name", "").upper() == symbol), None)
    
    if idx is None:
        raise ValueError(f"Unknown perp symbol: {symbol}")
    
    return idx
