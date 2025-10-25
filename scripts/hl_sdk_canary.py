# file: scripts/hl_sdk_canary.py
import os, json, time, httpx
from hexbytes import HexBytes
from eth_keys import keys
from hyperliquid.utils.signing import sign_l1_action  # use the SDK's canonical signer

REST = os.environ.get("HL_REST_MAIN", "https://api.hyperliquid.xyz")
MASTER = os.environ["HL_ACCOUNT_ADDRESS"]
AGENT_ADDR = os.environ["HL_API_WALLET_ADDRESS"]
PRIV = os.environ["HL_PRIVATE_KEY"]

# Derive and assert agent key matches env
derived = keys.PrivateKey(HexBytes(PRIV)).public_key.to_checksum_address()
assert derived.lower() == AGENT_ADDR.lower(), f"Key→addr mismatch: {derived} vs {AGENT_ADDR}"

# Build short-form action: IOC "market-style" (p:"0"), BTC asset id=0
action = {
    "type": "order",
    "orders": [{
        "a": 0,                  # BTC
        "b": True,               # buy
        "p": "0",                # market-style IOC
        "r": False,              # reduceOnly
        "s": "0.0001",           # size as string, no trailing zeros
        "t": {"limit": {"tif": "Ioc"}}
    }],
    "grouping": "na",
}

nonce = int(time.time() * 1000)

# Canonical SDK signing for L1 action (no vault/expires for simple order)
from eth_account import Account
wallet = Account.from_key(PRIV)
sig = sign_l1_action(wallet, action, None, nonce, None, True)  # is_mainnet=True

envelope = {"action": action, "nonce": nonce, "signature": sig}

# Show quick identity + envelope preview
print("[ID]", "agent", AGENT_ADDR, "master", MASTER)
print("[ENV]", json.dumps(envelope, separators=(",", ":"))[:240] + "...")

# Post to /exchange
resp = httpx.post(f"{REST}/exchange", json=envelope, timeout=15)
print("[HTTP]", resp.status_code, resp.text)
