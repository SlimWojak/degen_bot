#!/usr/bin/env python3
"""
L1 Layout Probe - Test both action-first and nonce-first msgpack layouts
"""
import json, time, hashlib, msgpack
from hexbytes import HexBytes
from eth_keys import keys
import httpx
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from common.config import load_config

def build_short_action(asset_id: int, is_buy: bool, sz_str: str, px_str: str = None,
                       tif: str = "Ioc", reduce_only: bool = False, grouping: str = "na") -> dict:
    """Build short-form action with strict types."""
    order = {
        "a": int(asset_id),                              # int
        "b": bool(is_buy),                               # bool
        "p": "0" if px_str is None else str(px_str),     # string
        "r": bool(reduce_only),                          # bool
        "s": str(sz_str),                                # string
        "t": {"limit": {"tif": tif}},                    # object
    }
    return {
        "type": "order",
        "orders": [order],
        "grouping": grouping,
    }

def sign_and_post(envelope, label, config):
    """Sign envelope and POST to /exchange, return results."""
    try:
        # Msgpack with exact options
        packed = msgpack.packb(envelope, use_bin_type=False, strict_types=True)
        digest = hashlib.sha256(packed).digest()
        digest_hex = "0x" + digest.hex()
        
        # Sign with eth_keys
        sk = keys.PrivateKey(HexBytes(config.hl.private_key))
        sig = sk.sign_msg_hash(digest)
        v = 27 if sig.v in (0, 27) else 28
        
        r_hex = "0x" + sig.r.to_bytes(32, "big").hex()
        s_hex = "0x" + sig.s.to_bytes(32, "big").hex()
        
        # Build final envelope
        final_envelope = {
            "action": envelope["action"],
            "nonce": envelope["nonce"],
            "signature": {"r": r_hex, "s": s_hex, "v": v}
        }
        
        # Local recovery check
        v_local = v - 27 if v >= 27 else v
        sig_local = keys.Signature(vrs=(v_local, int(r_hex, 16), int(s_hex, 16)))
        pub = sig_local.recover_public_key_from_msg_hash(digest)
        local_recovered = pub.to_checksum_address().lower()
        
        # POST to /exchange
        async def post_exchange():
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{config.hl.rest_url}/exchange", json=final_envelope)
                return resp.status_code, resp.text
        
        import asyncio
        status_code, body = asyncio.run(post_exchange())
        
        # Parse server error address
        server_err_addr = None
        if "User or API Wallet" in body:
            import re
            match = re.search(r"User or API Wallet (0x[a-fA-F0-9]{40}) does not exist", body)
            if match:
                server_err_addr = match.group(1).lower()
        
        return {
            "label": label,
            "packed_hex": packed.hex()[:200],
            "digest_hex": digest_hex,
            "local_recovered": local_recovered,
            "server_err_addr": server_err_addr,
            "http_status": status_code,
            "body": body[:500],
            "match_local": local_recovered == config.hl.api_wallet.lower(),
            "match_server": server_err_addr == config.hl.api_wallet.lower() if server_err_addr else False
        }
        
    except Exception as e:
        return {
            "label": label,
            "error": str(e),
            "match_local": False,
            "match_server": False
        }

def main():
    config = load_config()
    
    # Build short-form action
    action = build_short_action(
        asset_id=0,  # BTC
        is_buy=True,
        sz_str="0.0001",  # Small size for testing
        px_str=None,  # Market-style IOC
        tif="Ioc",
        reduce_only=False,
        grouping="na"
    )
    
    nonce = int(time.time() * 1000)
    
    print(f"[HL:probe] Testing layouts for agent {config.hl.api_wallet}")
    print(f"[HL:probe] Master: {config.hl.account}")
    print(f"[HL:probe] REST: {config.hl.rest_url}")
    print()
    
    # Layout A: action-first
    envelope_a = {"action": action, "nonce": nonce}
    result_a = sign_and_post(envelope_a, "action-first", config)
    
    # Layout B: nonce-first  
    envelope_b = {"nonce": nonce, "action": action}
    result_b = sign_and_post(envelope_b, "nonce-first", config)
    
    # Print results
    for result in [result_a, result_b]:
        print(f"[{result['label']}]")
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  packed_hex: {result['packed_hex']}")
            print(f"  digest: {result['digest_hex']}")
            print(f"  local_recovered: {result['local_recovered']}")
            print(f"  server_err_addr: {result['server_err_addr']}")
            print(f"  match_local: {result['match_local']}")
            print(f"  match_server: {result['match_server']}")
            print(f"  http_status: {result['http_status']}")
            print(f"  body: {result['body']}")
        print()
    
    # Summary
    print("SUMMARY:")
    print(f"Layout A (action-first): local={result_a.get('match_local', False)}, server={result_a.get('match_server', False)}")
    print(f"Layout B (nonce-first): local={result_b.get('match_local', False)}, server={result_b.get('match_server', False)}")
    
    # Determine which layout works
    if result_a.get('match_server', False):
        print("✅ Layout A (action-first) is correct")
    elif result_b.get('match_server', False):
        print("✅ Layout B (nonce-first) is correct")
    else:
        print("❌ Neither layout matches server expectations")

if __name__ == "__main__":
    main()