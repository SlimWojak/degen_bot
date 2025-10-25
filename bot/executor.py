"""
Degen God v2 Order Executor.

Clean SDK-based implementation using asset IDs and proper string formatting.
"""

import asyncio
import json
import math
import logging
import time
import httpx
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.signing import get_timestamp_ms
from common.formatting import to_decimal_str
from eth_utils import keccak
from eth_keys import keys

# NOTE: the signing util name can vary by SDK version.
# Try these in order; keep only the one that exists in your environment:
try:
    from hyperliquid.utils.signing import sign_order as _sign_action   # common name in examples
except Exception:
    try:
        from hyperliquid.utils.signing import sign_action as _sign_action
    except Exception:
        try:
            from hyperliquid.utils.signing import sign as _sign_action
        except Exception:
            try:
                from hyperliquid.utils.signing import sign_message as _sign_action
            except Exception:
                _sign_action = None

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Clean SDK-based order executor using asset IDs and proper formatting."""
    
    def __init__(self, account_address: str, signer_private_key: str, base_url: str = None):
        """
        Initialize the order executor with proper SDK configuration.
        
        Args:
            account_address: Master (funded) account address
            signer_private_key: API wallet private key for signing
            base_url: Hyperliquid API base URL (optional)
        """
        # Use eth_keys for address derivation (no eth_account)
        from eth_keys import keys
        from hexbytes import HexBytes
        
        self.account_address = account_address.lower()
        self.signer_private_key = signer_private_key
        sk = keys.PrivateKey(HexBytes(signer_private_key))
        self.signer_address = sk.public_key.to_checksum_address().lower()
        
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = constants.MAINNET_API_URL
            
        self.exchange = Exchange(
            {"account_address": self.account_address, "secret_key": self.signer_private_key},
            base_url=self.base_url,
        )
        self.info = Info(base_url=self.base_url)
        
        # Legacy attributes for compatibility
        self.account = self.account_address
        self.sk = self.signer_private_key
        self.mainnet = "mainnet" in self.base_url
        
        logger.info(f"[HL:init] master={self.account_address} api_wallet={self.signer_address}")
        logger.info(f"[HL:init] exchange_account={self.account_address} exchange_signer={self.signer_address}")

    # Old SDK signing method removed - using pure eth_keys signer now

    def _asset_id(self, coin: str) -> int:
        """Get asset ID for a coin."""
        meta = self.info.meta()
        assets = meta["universe"]
        asset = next((i for i, a in enumerate(assets)
                      if a.get("name") == coin or a.get("spotName") == coin), None)
        if asset is None:
            raise ValueError(f"Asset not found for {coin}. Universe: {[a.get('name') for a in assets]}")
        return asset

    def _tick_lot(self, coin: str):
        """Return (tick, lot, sz_decimals, px_decimals) from meta; fall back to sensible defaults."""
        try:
            meta = self.info.meta()
            print(f"[_tick_lot] Meta type: {type(meta)}, value: {meta}")
            
            if not isinstance(meta, dict):
                print(f"[_tick_lot] Meta is not a dict, using fallback")
                return 0.01, 1e-6, 5, 1
                
            assets = meta.get("universe", [])
            print(f"[_tick_lot] Assets: {assets}")
            
            for a in assets:
                if a.get("name") == coin or a.get("spotName") == coin:
                    print(f"[_tick_lot] Found asset: {a}")
                    # hyperliquid meta can vary — try common paths:
                    # For BTC: szDecimals=5 means 5 decimal places for size
                    # For BTC: no explicit tick size, use 0.01 as default
                    tick = float(a.get("minTick", 0)) or 0.01
                    sz_decimals = int(a.get("szDecimals", 5))  # e.g., 5 for BTC
                    # Convert szDecimals to actual lot size (e.g., 5 decimals = 0.00001)
                    lot = 10 ** (-sz_decimals)
                    # Price decimals: max(0, 6 - szDecimals) as per docs
                    px_decimals = max(0, 6 - sz_decimals)
                    print(f"[_tick_lot] Calculated tick: {tick}, lot: {lot}, sz_decimals: {sz_decimals}, px_decimals: {px_decimals}")
                    return max(tick, 1e-8), max(lot, 1e-12), sz_decimals, px_decimals
        except Exception as e:
            print(f"[_tick_lot] Error: {e}")
            
        # fallback
        print(f"[_tick_lot] Using fallback values")
        return 0.01, 1e-6, 5, 1

    def _round_to_tick(self, px: float, tick: float) -> float:
        if tick <= 0: 
            return px
        return round(round(px / tick) * tick, 8)

    def _round_to_lot(self, sz: float, lot: float) -> float:
        if lot <= 0:
            return sz
        steps = max(1, int((sz + 1e-12) / lot))
        return round(steps * lot, 12)

    def _best_book(self, coin: str):
        """
        Return (bid, ask) as floats.
        Supports:
          - SDK l2_snapshot dict: {'coin','time','levels':[{'px': '...'}, ...]}
          - SDK l2_snapshot list forms: [ {'levels':[...]} ] or [ [ {..},{..} ] ]
          - RAW /info l2Book: {'levels': [...] } or {'bids': [...], 'asks': [...]}
        """
        # --- 1) SDK l2_snapshot (all shapes) ---
        try:
            snap = self.info.l2_snapshot(coin)
            print(f"[_best_book] SDK l2_snapshot raw response: {json.dumps(snap)[:500]}")

            # dict form
            if isinstance(snap, dict) and "levels" in snap:
                levels = snap["levels"]
                if isinstance(levels, list) and levels:
                    # Handle nested list: levels = [[{...}, {...}]]
                    if isinstance(levels[0], list):
                        level_data = levels[0]
                        if level_data:
                            bid = float(level_data[0]["px"])
                            ask = float(level_data[1]["px"]) if len(level_data) > 1 else bid * 1.001
                            return bid, ask
                    # Handle flat list: levels = [{...}, {...}]
                    else:
                        bid = float(levels[0]["px"])
                        ask = float(levels[1]["px"]) if len(levels) > 1 else bid * 1.001
                        return bid, ask

            # list-of-dict form: [ {'levels': [...] } ]
            if isinstance(snap, list) and snap and isinstance(snap[0], dict):
                levels = snap[0].get("levels") or []
                if levels:
                    bid = float(levels[0]["px"])
                    ask = float(levels[1]["px"]) if len(levels) > 1 else bid * 1.001
                    return bid, ask

            # nested list form: [ [ { 'px':.. }, { 'px':.. } ] ]
            if isinstance(snap, list) and snap and isinstance(snap[0], list):
                levels = snap[0]
                if levels:
                    bid = float(levels[0]["px"])
                    ask = float(levels[1]["px"]) if len(levels) > 1 else bid * 1.001
                    return bid, ask
        except Exception as e:
            print(f"[_best_book] SDK l2_snapshot parse fail: {repr(e)}")

        # --- 2) RAW /info l2Book (both 'levels' and 'bids/asks' forms) ---
        base_url = self.base_url.rstrip("/")
        try:
            r = httpx.post(f"{base_url}/info", json={"type": "l2Book", "coin": coin}, timeout=3.0)
            r.raise_for_status()
            data = r.json()
            print(f"[_best_book] RAW l2Book response: {json.dumps(data)[:500]}")

            # levels form
            levels = data.get("levels")
            if isinstance(levels, list) and levels:
                # Handle nested list: levels = [[{...}, {...}]]
                if isinstance(levels[0], list):
                    level_data = levels[0]
                    if level_data:
                        bid = float(level_data[0]["px"])
                        ask = float(level_data[1]["px"]) if len(level_data) > 1 else bid * 1.001
                        return bid, ask
                # Handle flat list: levels = [{...}, {...}]
                else:
                    bid = float(levels[0]["px"])
                    ask = float(levels[1]["px"]) if len(levels) > 1 else bid * 1.001
                    return bid, ask

            # bids/asks form
            bids, asks = data.get("bids"), data.get("asks")
            if isinstance(bids, list) and bids and isinstance(asks, list) and asks:
                def px(x):
                    # [px, sz] or {'px':..., 'sz':...}
                    return float(x[0] if isinstance(x, list) else x.get("px"))
                return px(bids[0]), px(asks[0])
        except Exception as e:
            print(f"[_best_book] RAW l2Book fail: {repr(e)}")

        raise ValueError(f"Unable to fetch bid/ask for {coin}")

    def _parse_oid(self, resp):
        """
        Parse OID from Hyperliquid response format.
        Handles: resting, filled, error responses with proper structure.
        """
        # 1) plain int
        if isinstance(resp, int):
            return resp

        # 2) try wrapped response paths
        try_paths = [
            ("response", "data", "statuses"),
            ("data", "statuses"),
            ("statuses",),
        ]

        statuses = None
        if isinstance(resp, dict):
            for path in try_paths:
                cur = resp
                ok = True
                for key in path:
                    if isinstance(cur, dict) and key in cur:
                        cur = cur[key]
                    else:
                        ok = False
                        break
                if ok:
                    statuses = cur
                    break

        # 3) iterate statuses array and look for OID
        if isinstance(statuses, list) and statuses:
            first = statuses[0]
            if isinstance(first, dict):
                # Check for different response types: 'resting', 'filled', 'error'
                for key in ['resting', 'filled', 'error']:
                    if key in first:
                        obj = first[key]
                        if isinstance(obj, dict) and "oid" in obj:
                            return obj["oid"]

        return None

    async def _sdk_order_single(self, order_spec: dict):
        """Try single-order path with correct SDK signature."""
        print("[order] Exchange.order:", order_spec)
        try:
            # Get coin name from asset ID
            asset_id = order_spec["asset"]
            meta = self.info.meta()
            universe = meta["universe"]
            coin_name = universe[asset_id]["name"]
            
            # Convert string values to float for SDK
            sz_float = float(order_spec["sz"])
            limit_px_float = float(order_spec["limit_px"])
            
            # Use correct SDK method signature
            resp = self.exchange.order(
                name=coin_name,
                is_buy=order_spec["is_buy"],
                sz=sz_float,
                limit_px=limit_px_float,
                order_type=order_spec["order_type"],
                reduce_only=order_spec.get("reduce_only", False)
            )
            print("[order] single type:", type(resp).__name__, "val:", repr(resp)[:300])
            return resp
        except Exception as e:
            print("[order] single EXC:", repr(e))
            return None

    async def _sdk_order_bulk(self, order_spec: dict):
        """Try bulk path with a single order."""
        try:
            # Convert asset to coin name for bulk orders
            asset_id = order_spec["asset"]
            meta = self.info.meta()
            universe = meta["universe"]
            coin_name = universe[asset_id]["name"]
            
            # Create bulk order spec with proper types
            bulk_spec = {
                "coin": coin_name,
                "is_buy": order_spec["is_buy"],
                "sz": float(order_spec["sz"]),  # Convert to float
                "limit_px": float(order_spec["limit_px"]),  # Convert to float
                "order_type": order_spec["order_type"],
                "reduce_only": order_spec.get("reduce_only", False)
            }
            
            resp = self.exchange.bulk_orders([bulk_spec])
            print("[order] bulk type:", type(resp).__name__, "val:", repr(resp)[:300])
            return resp
        except Exception as e:
            print("[order] bulk EXC:", repr(e))
            return None

    async def _raw_signed_order(self, coin: str, is_buy: bool, limit_px: str, sz: str, reduce_only: bool):
        """Raw signed order using Hyperliquid short-form schema with pure msgpack signing."""
        try:
            # Import helpers
            from common.hl_meta import get_asset_id
            from common.hl_l1_sign import sign_l1_envelope
            from common.hl_signing import canon_json, build_short_action
            import time
            
            # Get asset ID for the symbol
            asset_id = await get_asset_id(coin, self.base_url)
            
            # Build action with explicit ordering and strict types
            action = build_short_action(
                asset_id=int(asset_id),
                is_buy=bool(is_buy),
                sz_str=str(sz),
                px_str=None,  # Market-style IOC must send p:"0"
                tif="Ioc",
                reduce_only=bool(reduce_only),
                grouping="na"
            )

            # Sign with pure msgpack + sha256
            nonce = int(time.time() * 1000)
            envelope, packed, digest, digest_hex = sign_l1_envelope(
                self.signer_private_key,
                action,
                nonce
            )
            
            # Optional local recovery check (good to log once):
            from common.hl_l1_sign import recover_addr_from_sig
            rec = recover_addr_from_sig(digest,
                                        envelope["signature"]["r"],
                                        envelope["signature"]["s"],
                                        envelope["signature"]["v"])
            logger.info("[HL:addr] api=%s recovered=%s match=%s",
                        self.signer_address.lower(), rec, rec == self.signer_address.lower())
            
            # Log the packed bytes, digest and final payload
            logger.info(f"[HL:packed_hex] {packed.hex()[:256]}")  # first bytes for diffing
            # Compare against SDK's canonical payload construction (diagnostic only)
            try:
                from hyperliquid.utils.signing import l1_payload
                sdk_packed = l1_payload(envelope["action"], envelope["nonce"])  # bytes
                logger.info(f"[HL:packed_hex:SDK] {sdk_packed.hex()[:256]}")
                logger.info(f"[HL:packed_equal] {sdk_packed == packed}")
            except Exception as _e:
                logger.info(f"[HL:packed_hex:SDK] unavailable: {_e}")
            logger.info(f"[HL:digest] {digest_hex}")
            import json
            logger.info(f"[HL:envelope] {json.dumps(envelope, separators=(',', ':'), sort_keys=True)}")
            
            # Add preflight logging with strict field order
            order = action['orders'][0]
            logger.info(f"[HL:preflight] asset_id={order['a']} isBuy={order['b']} sz={order['s']} price={order['p']} reduceOnly={order['r']} tif={order['t']['limit']['tif']}")
            
            # Send the signed envelope using proper JSON formatting
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    resp = await client.post(
                        f"{self.base_url}/exchange",
                        json=envelope,
                    )
                    body = resp.text
                    try:
                        resp.raise_for_status()
                    finally:
                        logger.info(f"[HL:resp] http={resp.status_code} body={body[:1024]}")
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "ok":
                            return {"status": "ok", "data": data.get("data", {})}
                        else:
                            return {"status": "err", "response": data.get("response", "Unknown error")}
                    else:
                        return {"status": "err", "response": f"HTTP {resp.status_code}: {body}"}
                except httpx.HTTPStatusError as e:
                    body = e.response.text
                    logger.error(f"[HL:422] {body}")
                    return {"status": "err", "response": f"HTTP {e.response.status_code}: {body}"}
                    
        except Exception as e:
            logger.error(f"[order] L1 signing error: {e}")
            return {"status": "err", "response": str(e)}

    async def place_order(self, coin="BTC", usd_amount=10.0, is_buy=True):
        """Place an order with multiple fallback strategies."""
        print(f"[place_order] Starting order for {coin}, {usd_amount} USD, is_buy={is_buy}")
        
        asset = self._asset_id(coin)
        print(f"[place_order] Asset ID: {asset}")
        
        # bypass leverage (previous problems)
        bid, ask = self._best_book(coin)
        print(f"[place_order] Bid: {bid}, Ask: {ask}")
        
        ref = ask if is_buy else bid
        
        # Get tick, lot, and decimal places for proper formatting
        tick, lot, sz_decimals, px_decimals = self._tick_lot(coin)
        print(f"[place_order] Tick: {tick}, Lot: {lot}, sz_decimals: {sz_decimals}, px_decimals: {px_decimals}")
        
        # Calculate IOC price with tiny epsilon (as per docs)
        if is_buy:
            limit_px_float = bid * (1 + 5e-6)  # tiny epsilon for buy
        else:
            limit_px_float = ask * (1 - 5e-6)  # tiny epsilon for sell
        
        # Round to tick and format as decimal string
        limit_px_float = self._round_to_tick(limit_px_float, tick)
        limit_px = to_decimal_str(limit_px_float, px_decimals)
        
        # Calculate size and format as decimal string
        notional = max(usd_amount, 10.0)
        mid_price = (bid + ask) / 2
        qty = notional / mid_price
        qty = self._round_to_lot(qty, lot)
        sz = to_decimal_str(qty, sz_decimals)
        
        print(f"[place_order] Limit price: {limit_px}, Size: {sz}")

        order_spec = {
            "asset": asset,
            "is_buy": bool(is_buy),
            "reduce_only": False,
            "limit_px": limit_px,
            "sz": sz,
            "order_type": {"limit": {"tif": "Ioc"}},
        }
        
        print(f"[place_order] Order spec: {order_spec}")

        # Bypass SDK completely - go straight to raw signed order
        raw = await self._raw_signed_order(coin, is_buy, limit_px, sz, reduce_only=False)
        oid = self._parse_oid(raw)
        return {"oid": oid, "raw": raw}

    async def place_reduce_only(self, coin="BTC", usd_amount=10.0, side_long=True):
        """Place a reduce-only order to close position."""
        asset = self._asset_id(coin)
        bid, ask = self._best_book(coin)
        ref = bid if side_long else ask
        
        # Get tick, lot, and decimal places for proper formatting
        tick, lot, sz_decimals, px_decimals = self._tick_lot(coin)
        
        # Calculate aggressive IOC price for exit
        is_buy = not side_long
        if is_buy:
            limit_px_float = bid * (1 - 5e-6)  # tiny epsilon for buy exit
        else:
            limit_px_float = ask * (1 + 5e-6)  # tiny epsilon for sell exit
        
        # Round to tick and format as decimal string
        limit_px_float = self._round_to_tick(limit_px_float, tick)
        limit_px = to_decimal_str(limit_px_float, px_decimals)
        
        # Calculate size and format as decimal string
        notional = max(usd_amount, 10.0)
        mid_price = (bid + ask) / 2
        qty = notional / mid_price
        qty = self._round_to_lot(qty, lot)
        sz = to_decimal_str(qty, sz_decimals)

        order_spec = {
            "asset": asset,
            "is_buy": is_buy,
            "reduce_only": True,
            "limit_px": limit_px,
            "sz": sz,
            "order_type": {"limit": {"tif": "Ioc"}},
        }

        # Bypass SDK completely - go straight to raw signed order
        raw = await self._raw_signed_order(coin, is_buy, limit_px, sz, reduce_only=True)
        oid = self._parse_oid(raw)
        return {"oid": oid, "raw": raw}

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            # Use SDK cancel method
            result = await self.exchange.cancel(order_id)
            logger.info(f"📥 Cancel order response: {result}")
            
            if result.get('status') == 'ok':
                logger.info(f"✅ Order {order_id} cancelled successfully")
                return True
            else:
                logger.warning(f"⚠️  Cancel order result: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False