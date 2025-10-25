# scripts/probe_env.py
import json
import sys
import os

# Add parent directory to path so we can import common
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.config import load_config, redacted

if __name__ == "__main__":
    try:
        cfg = load_config()
        print(json.dumps(redacted(cfg), indent=2))
    except SystemExit as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(e.code)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
