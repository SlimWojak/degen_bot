import hashlib
import msgpack
import json
import copy
import logging
from hexbytes import HexBytes
from eth_keys import keys
from eth_account import Account

logger = logging.getLogger(__name__)

def _canonicalize_action(action):
    """Recursively sort all dict keys alphabetically and normalize types"""
    if isinstance(action, dict):
        # Sort keys alphabetically
        sorted_dict = {}
        for key in sorted(action.keys()):
            sorted_dict[key] = _canonicalize_action(action[key])
        return sorted_dict
    elif isinstance(action, list):
        return [_canonicalize_action(item) for item in action]
    elif isinstance(action, bool):
        # Keep booleans as booleans
        return action
    elif isinstance(action, int):
        # Keep integers as integers
        return action
    elif isinstance(action, float):
        # Convert floats to string, remove trailing zeros
        return str(action).rstrip('0').rstrip('.')
    elif isinstance(action, str):
        # Ensure addresses are lowercase
        if action.startswith('0x') and len(action) == 42:
            return action.lower()
        return action
    else:
        return action

def sign_l1_envelope(secret_key_hex: str, action: dict, nonce: int):
    """
    Build envelope {action, nonce, signature} for HL L1 using strict field order:
      OrderedDict as-is + msgpack + keccak (exactly like SDK)
    """
    # Step 1: Use action as-is (OrderedDict preserves field order)
    logger.info("[HL:action-original] %s", json.dumps(action, separators=(",",":")))
    
    # Step 2: Convert OrderedDict to regular dict before packing
    def _to_regular_dict(obj):
        """Recursively convert OrderedDict to regular dict"""
        if isinstance(obj, dict):
            return {k: _to_regular_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_to_regular_dict(item) for item in obj]
        else:
            return obj
    
    regular_action = _to_regular_dict(action)
    logger.info("[HL:action-regular] %s", json.dumps(regular_action, separators=(",",":")))
    
    # Step 3: Pack with SDK's exact options
    packed = msgpack.packb(
        regular_action,
        use_bin_type=True,
        strict_types=True,
        default=str
    )
    
    # Step 4: Add nonce as 8-byte big-endian (same as SDK)
    data = packed + nonce.to_bytes(8, "big")
    
    # Step 5: For L1 orders: vault_address=None, expires_after=None
    # So we add the null byte (same as SDK when vault_address is None)
    data += b"\x00"
    # No expires_after for L1 orders
    
    # Step 6: Use keccak like the SDK (this should match Hyperliquid's expectation)
    from hyperliquid.utils.signing import keccak
    digest = keccak(data)
    digest_hex = "0x" + digest.hex()
    
    logger.info("[CANON OK] Using strict field order digest=%s", digest.hex())
    logger.info("[CANON OK] Packed hex=%s", packed.hex()[:200])
    logger.info("[HL:action-regular] %s", json.dumps(regular_action, separators=(",",":")))
    
    # Step 9: Compare with SDK's action hash for byte-for-byte verification
    try:
        from hyperliquid.utils.signing import action_hash as sdk_action_hash
        sdk_digest = sdk_action_hash(regular_action, None, nonce, None)
        sdk_digest_hex = "0x" + sdk_digest.hex()
        logger.info("[HL:SDK-digest] %s", sdk_digest_hex)
        logger.info("[HL:digest-match] %s", digest_hex == sdk_digest_hex)
        if digest_hex != sdk_digest_hex:
            logger.error("[HL:BYTE-MISMATCH] Our digest != SDK digest")
            logger.error("[HL:our-packed] %s", packed.hex()[:200])
            # Try to get SDK's packed bytes for comparison
            try:
                from hyperliquid.utils.signing import l1_payload
                sdk_packed = l1_payload(regular_action, nonce)
                logger.error("[HL:sdk-packed] %s", sdk_packed.hex()[:200])
            except Exception as e:
                logger.error("[HL:sdk-packed] unavailable: %s", e)
    except Exception as e:
        logger.error("[HL:SDK-comparison] failed: %s", e)
    
    # Step 6: Sign with eth_keys
    sk = keys.PrivateKey(HexBytes(secret_key_hex))
    sig = sk.sign_msg_hash(digest)
    v = 27 if sig.v in (0, 27) else 28
    
    r_hex = "0x" + sig.r.to_bytes(32, "big").hex()
    s_hex = "0x" + sig.s.to_bytes(32, "big").hex()
    
    # Step 10: Build envelope with regular action (converted from OrderedDict)
    envelope = {
        "action": regular_action,
        "nonce": int(nonce),
        "signature": {"r": r_hex, "s": s_hex, "v": v},
    }
    
    # Deep-copy for send to guarantee no later mutation
    to_send = copy.deepcopy(envelope)
    
    logger.info("[HL:envelope] %s", json.dumps(to_send, separators=(",",":")))
    
    return envelope, packed, digest, digest_hex


def recover_addr_from_sig(digest: bytes, r_hex: str, s_hex: str, v_val: int) -> str:
    # Convert v from {27,28} to {0,1} for eth_keys.Signature
    v = 0 if v_val in (0, 27) else 1
    sig = keys.Signature(vrs=(v, int(r_hex, 16), int(s_hex, 16)))  # v,r,s order
    pub = sig.recover_public_key_from_msg_hash(digest)
    return pub.to_checksum_address().lower()


# Legacy wrapper for backward compatibility
def sign_envelope_l1(secret_key: str, action: dict, nonce: int = None, is_mainnet: bool = True):
    """
    Legacy wrapper for backward compatibility.
    """
    import time
    if nonce is None:
        nonce = int(time.time() * 1000)
    
    return sign_l1_envelope(secret_key, action, nonce)