# backend/config.py
from dotenv import load_dotenv, find_dotenv
import os
import logging

# Load nearest .env from project tree, don't override existing process env
load_dotenv(find_dotenv(usecwd=True), override=False)

logger = logging.getLogger(__name__)

class Settings:
    """Unified configuration with deprecation mapping."""
    
    # Core Hyperliquid settings
    HL_NETWORK = (os.getenv("HL_NETWORK") or os.getenv("HL_ENV") or "testnet").strip().lower()
    HL_ACCOUNT_ADDRESS = (os.getenv("HL_ACCOUNT_ADDRESS") or "").strip()
    HL_PRIVATE_KEY = (os.getenv("HL_PRIVATE_KEY") or "").strip()
    HL_SYMBOL = (os.getenv("HL_SYMBOL") or "ETH").strip().upper()
    HL_NOTIONAL_USD = float(os.getenv("HL_NOTIONAL_USD", "15"))
    HL_EXIT_AFTER_SECONDS = int(os.getenv("HL_EXIT_AFTER_SECONDS", "5"))
    
    # Live data configuration
    DATA_SOURCE = (os.getenv("DATA_SOURCE") or "mock").strip().lower()
    STATE_CACHE_MS = int(os.getenv("STATE_CACHE_MS", "800"))
    HL_DEFAULT_SYMBOL = (os.getenv("HL_DEFAULT_SYMBOL") or "ETH").strip().upper()
    
    # Trading configuration
    HL_TRADING_ENABLED = os.getenv("HL_TRADING_ENABLED", "false").strip().lower() == "true"
    HL_MAX_NOTIONAL_USD = float(os.getenv("HL_MAX_NOTIONAL_USD", "50"))
    HL_MAX_CROSS_BPS = float(os.getenv("HL_MAX_CROSS_BPS", "200"))  # 2% max cross
    
    # Signer implementation
    HL_SIGNER_IMPL = (os.getenv("HL_SIGNER_IMPL") or "sdk").strip().lower()
    
    # Status check timeouts
    STATUS_TIMEOUT_MS = int(os.getenv("STATUS_TIMEOUT_MS", "400"))
    STATUS_TOTAL_TIMEOUT_MS = int(os.getenv("STATUS_TOTAL_TIMEOUT_MS", "900"))
    
    # DeepSeek AI Agent configuration
    DEEPSEEK_API_BASE = (os.getenv("DEEPSEEK_API_BASE") or "").strip()
    DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    DEEPSEEK_MODEL = (os.getenv("DEEPSEEK_MODEL") or "deepseek-chat").strip()
    DEEPSEEK_TIMEOUT_MS = int(os.getenv("DEEPSEEK_TIMEOUT_MS", "5000"))
    AGENT_DECISION_COOLDOWN_MS = int(os.getenv("AGENT_DECISION_COOLDOWN_MS", "1500"))
    
    # DeepSeek Decision Configuration
    DEEPSEEK_DECISION_MAX_INPUT_CHARS = int(os.getenv("DEEPSEEK_DECISION_MAX_INPUT_CHARS", "2000"))
    DECISION_RETRY_MAX = int(os.getenv("DECISION_RETRY_MAX", "2"))
    DECISION_RETRY_BASE_MS = int(os.getenv("DECISION_RETRY_BASE_MS", "250"))
    
    # Market Sampler Configuration
    DEBUG_SAMPLER = os.getenv("DEBUG_SAMPLER", "false").strip().lower() == "true"
    
    # Live Guard Configuration
    LIVE_GUARD = os.getenv("LIVE_GUARD", "true").strip().lower() == "true"
    
    # WebSocket Implementation Configuration
    HL_WS_IMPL = os.getenv("HL_WS_IMPL", "unified").strip().lower()
    
    # Agent trading configuration (canonical symbols)
    AGENT_SYMBOLS = (os.getenv("AGENT_SYMBOLS") or "BTC,ETH,SOL").strip()
    AGENT_MODE = (os.getenv("AGENT_MODE") or "shadow").strip()
    AGENT_DEFAULT_NOTIONAL_USD = float(os.getenv("AGENT_DEFAULT_NOTIONAL_USD", "15"))
    AGENT_PER_SYMBOL_COOLDOWN_MS = int(os.getenv("AGENT_PER_SYMBOL_COOLDOWN_MS", "10000"))
    AGENT_MAX_TRADES_PER_DAY = int(os.getenv("AGENT_MAX_TRADES_PER_DAY", "300"))
    AGENT_MAX_DRAWDOWN_PCT = float(os.getenv("AGENT_MAX_DRAWDOWN_PCT", "10"))
    AGENT_POSITION_RISK_PCT = float(os.getenv("AGENT_POSITION_RISK_PCT", "2"))
    
    # Market WebSocket configuration
    MARKET_WS_ENABLED = os.getenv("MARKET_WS_ENABLED", "true").strip().lower() == "true"
    MARKET_WS_TICK_MS = int(os.getenv("MARKET_WS_TICK_MS", "200"))
    MARKET_WS_BOOK_DEPTH = int(os.getenv("MARKET_WS_BOOK_DEPTH", "10"))
    MARKET_WS_BUFFER_SECS = int(os.getenv("MARKET_WS_BUFFER_SECS", "120"))
    MARKET_MID_BUCKET_S = int(os.getenv("MARKET_MID_BUCKET_S", "1"))
    MARKET_MID_HISTORY_MIN = int(os.getenv("MARKET_MID_HISTORY_MIN", "60"))
    
    # Rate limiting configuration
    HL_RATE_INFO_RPS = float(os.getenv("HL_RATE_INFO_RPS", "10"))  # Info API calls per second
    HL_RATE_ORDER_RPS = float(os.getenv("HL_RATE_ORDER_RPS", "5"))  # Order API calls per second
    HL_RATE_BURST = int(os.getenv("HL_RATE_BURST", "20"))  # Burst capacity
    
    # WebSocket reconnection configuration
    HL_WS_MIN_RECONNECT_MS = int(os.getenv("HL_WS_MIN_RECONNECT_MS", "1000"))  # Minimum reconnect delay
    HL_WS_BACKOFF_MAX_MS = int(os.getenv("HL_WS_BACKOFF_MAX_MS", "30000"))  # Maximum backoff delay
    HL_WS_JITTER_MS = int(os.getenv("HL_WS_JITTER_MS", "1000"))  # Random jitter range
    
    # L2 snapshot cooldown
    HL_L2_COOLDOWN_MS = int(os.getenv("HL_L2_COOLDOWN_MS", "1000"))  # L2 snapshot cooldown per symbol

    # Legacy ASSETS support (deprecated)
    @property
    def ASSETS(self):
        """Legacy ASSETS property - use AGENT_SYMBOLS instead."""
        if os.getenv("ASSETS"):
            logger.warning("DEPRECATED: ASSETS is deprecated, use AGENT_SYMBOLS instead")
            return os.getenv("ASSETS").strip()
        return self.AGENT_SYMBOLS
    
    # Deprecation warnings
    def __init__(self):
        # Check for deprecated env vars
        if os.getenv("HL_ENV"):
            logger.warning("DEPRECATED: HL_ENV is deprecated, use HL_NETWORK instead")
        
        if os.getenv("HL_API_WALLET_ADDRESS"):
            logger.warning("DEPRECATED: HL_API_WALLET_ADDRESS is deprecated, use HL_ACCOUNT_ADDRESS instead")

settings = Settings()

def ws_url_for(network: str) -> str:
    """Get WebSocket URL for the given network."""
    if network.lower() == "mainnet":
        return "wss://api.hyperliquid.xyz/ws"
    elif network.lower() == "testnet":
        return "wss://api.hyperliquid-testnet.xyz/ws"
    else:
        logger.warning(f"Unknown network {network}, defaulting to testnet")
        return "wss://api.hyperliquid-testnet.xyz/ws"
