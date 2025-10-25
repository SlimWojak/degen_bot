import os, json, httpx

REST = os.environ.get("HL_REST_MAIN", "https://api.hyperliquid.xyz")
MASTER = os.environ["HL_ACCOUNT_ADDRESS"].lower()
AGENT  = os.environ["HL_API_WALLET_ADDRESS"].lower()

def post_info(payload):
    return httpx.post(
        f"{REST}/info",
        headers={"content-type": "application/json"},
        content=json.dumps(payload),
        timeout=10,
    )

def main():
    r1 = post_info({"type": "userRole", "user": AGENT})
    r2 = post_info({"type": "extraAgents", "user": MASTER})
    print("[env]", REST)
    print("[userRole(agent)]", r1.status_code, r1.text)
    print("[extraAgents(master)]", r2.status_code, r2.text)

if __name__ == "__main__":
    main()


