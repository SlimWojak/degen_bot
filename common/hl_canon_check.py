# common/hl_canon_check.py
from collections import OrderedDict
import msgpack, json, hashlib
from typing import Any, Mapping

def _sorted_map(obj: Any) -> Any:
    # Recursively sort all dict keys alphabetically and return plain dicts
    if isinstance(obj, dict):
        return {k: _sorted_map(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [ _sorted_map(x) for x in obj ]
    return obj

def pack_sha256_sorted(action: Mapping) -> bytes:
    """SDK-expected behavior for L1: sorted maps + msgpack + sha256 digest."""
    sorted_action = _sorted_map(action)
    packed = msgpack.packb(sorted_action, use_bin_type=True, strict_types=True)
    return hashlib.sha256(packed).digest()

def pack_hex(action: Mapping) -> str:
    sorted_action = _sorted_map(action)
    packed = msgpack.packb(sorted_action, use_bin_type=True, strict_types=True)
    return packed.hex()

def pretty(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)
