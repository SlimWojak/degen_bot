import json, time, hashlib, msgpack, sys
from pathlib import Path
# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hexbytes import HexBytes
from eth_keys import keys
from hyperliquid.utils.signing import recover_agent_or_user_from_l1_action
from common.config import load_config

cfg = load_config()
AGENT_ADDR = cfg.hl.api_wallet.lower()
MASTER_ADDR = cfg.hl.account.lower()
PRIV = cfg.hl.private_key

action = {
    "type": "order",
    "orders": [{
        "a": 0,
        "b": True,
        "p": "0",
        "r": False,
        "s": "0.00009",
        "t": {"limit": {"tif": "Ioc"}},
    }],
    "grouping": "na",
}

nonce = int(time.time() * 1000)
sk = keys.PrivateKey(HexBytes(PRIV))

def sign_and_recover(message_map, label):
    packed = msgpack.packb(message_map, use_bin_type=True)
    digest = hashlib.sha256(packed).digest()
    sig = sk.sign_msg_hash(digest)
    v = 27 if sig.v in (0, 27) else 28
    r_hex = "0x" + sig.r.to_bytes(32, "big").hex()
    s_hex = "0x" + sig.s.to_bytes(32, "big").hex()
    envelope = {"action": action, "nonce": nonce, "signature": {"r": r_hex, "s": s_hex, "v": v}}

    recovered = recover_agent_or_user_from_l1_action(
        action=envelope["action"],
        signature=envelope["signature"],
        active_pool=MASTER_ADDR,  # Installed SDK expects vault/address here
        nonce=envelope["nonce"],
        expires_after=envelope["nonce"] + 86_400_000,
        is_mainnet=True,
    )
    print(f"[{label}] packed_hex={packed.hex()[:200]}")
    print(f"[{label}] digest=0x{digest.hex()}")
    print(f"[{label}] recovered={recovered} match={recovered.lower()==AGENT_ADDR}")
    return recovered.lower() == AGENT_ADDR

ok_action_first = sign_and_recover({"action": action, "nonce": nonce}, "action-first")
ok_nonce_first = sign_and_recover({"nonce": nonce, "action": action}, "nonce-first")

print("RESULT => action-first:", ok_action_first, "nonce-first:", ok_nonce_first)
