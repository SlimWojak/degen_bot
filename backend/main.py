"""
Professional Trading Cockpit V2 - FastAPI Backend

Real-time trading dashboard with WebSocket updates.
Connects to existing data/trades.db with mock fallback.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
import pandas as pd
import numpy as np
import json
import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import sys
import httpx
import websockets
import time

from common.config import load_config, redacted
from common.action_schema import TradeAction
from bot.executor import OrderExecutor
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from eth_account import Account
from eth_utils import keccak
from eth_keys import keys
from backend.routes_hl import router as hl_router
from backend.routes_ai import router as ai_router
from backend.routes_agent import router as agent_router

# Import metrics and ops
from backend.observability.metrics import create_metrics_router
from backend.routes_ops import router as ops_router
from backend.routes_hl_audit import router as hl_audit_router
from backend.routes_ws_controls import router as ws_controls_router
from backend.routes_mind import router as mind_router
from backend.routes_dashboard import router as dashboard_router
from backend.services.market_feed_manager import market_feed_manager
from backend.services.rest_sampler import rest_sampler
from backend.system.peso_mind import peso_mind
from backend.config import settings, ws_url_for
from common.hl_client import connect, base_url_for
from backend.services.state_service import state_service
from backend.util.async_tools import shutdown_supervised_tasks
# Legacy MarketDataService removed - using unified HyperliquidWSClient
import importlib
import time
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
try:
    CFG = load_config()
    logger.info("Configuration loaded successfully")
    logger.info(f"[HL:init] env={CFG.hl.env} master={CFG.hl.account.lower()} api_wallet={CFG.hl.api_wallet.lower()}")
    logger.info(f"Environment: {CFG.hl.env}")
    logger.info(f"Assets: {CFG.bot.assets}")
except Exception as e:
    logger.error(f"Failed to load configuration: {e}")
    raise

app = FastAPI(title="DEGEN_GOD_V2 Trading Cockpit", version="2.0")

# Include HL routes
app.include_router(hl_router, prefix="/hl", tags=["hl"])

# Include AI trading routes
app.include_router(ai_router, prefix="/ai", tags=["ai-trading"])

# Include AI agent routes
app.include_router(agent_router, prefix="/agent", tags=["ai-agent"])

# Include metrics routes
metrics_router = create_metrics_router()
app.include_router(metrics_router)

# Include ops routes
app.include_router(ops_router)
app.include_router(hl_audit_router)
app.include_router(ws_controls_router)
app.include_router(mind_router)
app.include_router(dashboard_router)

# Include simulation routes
from backend.routes_sim import router as sim_router
app.include_router(sim_router)

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

# Market feed service (unified Hyperliquid client)
market_feed = None

def assert_no_legacy_ws():
    """Assert that no legacy WebSocket service is loaded."""
    import sys
    log = logging.getLogger("startup")
    
    if "backend.services.market_ws" in sys.modules:
        raise RuntimeError("legacy MarketDataService module loaded—cutover incomplete")
    
    if settings.HL_WS_IMPL != "unified":
        raise RuntimeError(f"HL_WS_IMPL must be 'unified' after cutover, got: {settings.HL_WS_IMPL}")
    
    log.info("[startup] legacy WS not loaded ✓")

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global market_feed
    
    # Assert no legacy WebSocket service is loaded
    assert_no_legacy_ws()
    
    # Setup log rotation
    try:
        from backend.observability.logs import setup_log_rotation
        setup_log_rotation()
    except Exception as e:
        logger.error(f"Log rotation setup error: {e}")
    
    # Initialize database first
    try:
        from backend.persistence.init_db import init_db, get_db_path
        db_path = get_db_path()
        if init_db(db_path):
            logger.info(f"Database initialized: {db_path}")
        else:
            logger.warning(f"Database initialization failed: {db_path}")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
    
    # Initialize unified Hyperliquid WebSocket service
    if settings.MARKET_WS_ENABLED:
        try:
            symbols = settings.AGENT_SYMBOLS.split(',')
            
            # Start unified Hyperliquid WebSocket client via manager
            await market_feed_manager.start()
            app.state.market_feed = market_feed_manager
            logger.info(f"Market feed manager started for symbols: {symbols}")
            
            # Start market sampler for data health monitoring
            from backend.services.market_sampler import start_market_sampler
            asyncio.create_task(start_market_sampler())
            logger.info("Market sampler started")
            
            # Start REST sampler for degraded mode
            await rest_sampler.start()
            logger.info("REST sampler started")
            
            # Start PesoMind orchestrator
            await peso_mind.start()
            logger.info("PesoMind orchestrator started")
            
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid WS client: {e}")
    else:
        logger.info("Market WS disabled, skipping initialization")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup services on shutdown."""
    try:
        # Stop PesoMind orchestrator
        await peso_mind.stop()
        logger.info("PesoMind orchestrator stopped")
        
        # Stop market feed manager
        await market_feed_manager.stop()
        logger.info("Market feed manager stopped")
        
        # Stop REST sampler
        await rest_sampler.stop()
        logger.info("REST sampler stopped")
        
        # Shutdown all supervised tasks
        await shutdown_supervised_tasks()
        logger.info("All supervised tasks shut down")
        
    except Exception as e:
        logger.error(f"Error stopping services: {e}")

def _authorized_agent_check(info: Info, owner_addr: str, signer_addr: str) -> dict:
    """
    Returns {"ok": True} if signer is authorized for owner; else {"ok": False, "reason": "..."}.
    Structure of extra_agents can vary; handle defensively.
    """
    try:
        agents = info.extra_agents(owner_addr)
        # common shapes:
        # 1) {"agents": [{"addr": "...", "validUntil": ...}, ...]}
        # 2) [{"addr": "...", "validUntil": ...}, ...]
        if isinstance(agents, dict) and "agents" in agents:
            agents = agents.get("agents", [])
        if not isinstance(agents, list):
            return {"ok": False, "reason": f"Unexpected extra_agents shape: {type(agents)}"}
        # normalize addresses (case-insensitive)
        signer_lower = signer_addr.lower()
        for a in agents:
            addr = (a.get("addr") or a.get("address") or "").lower()
            if addr == signer_lower:
                return {"ok": True}
        return {"ok": False, "reason": f"Signer {signer_addr} not found in extra_agents"}
    except Exception as e:
        return {"ok": False, "reason": f"extra_agents error: {e}"}

@app.on_event("startup")
def startup_preflight():
    log = logging.getLogger("preflight")
    network = settings.HL_NETWORK
    base_url = base_url_for(network)
    owner = settings.HL_ACCOUNT_ADDRESS
    pk = settings.HL_PRIVATE_KEY
    if not owner or not pk:
        raise RuntimeError("Missing HL_ACCOUNT_ADDRESS or HL_PRIVATE_KEY in environment")

    signer_addr = Account.from_key(pk).address

    # SDK version (best-effort)
    try:
        hl_mod = importlib.import_module("hyperliquid")
        sdk_version = getattr(hl_mod, "__version__", "unknown")
    except Exception:
        sdk_version = "unknown"

    # Only run preflight in live mode
    if settings.DATA_SOURCE == "live":
        try:
            # light connect + agent check
            _, info = connect(network, pk)
            agent_check = _authorized_agent_check(info, owner, signer_addr)
            # log everything helpful
            log.info(
                "HL preflight | network=%s base_url=%s owner=%s signer=%s sdk=%s agent_ok=%s reason=%s",
                network, base_url, owner, signer_addr, sdk_version, agent_check.get("ok"),
                agent_check.get("reason", "")
            )
            if not agent_check.get("ok"):
                raise RuntimeError(f"Signer not authorized for owner: {agent_check.get('reason')}")
        except Exception as e:
            log.warning(f"HL preflight failed: {e}")
            # Don't fail startup in mock mode
    else:
        log.info(f"HL preflight | SKIPPED (mock mode) network=%s base_url=%s owner=%s signer=%s sdk=%s", 
                network, base_url, owner, signer_addr, sdk_version)

@app.on_event("startup")
def _log_identities():
    CFG = load_config()
    try:
        derived = Account.from_key(CFG.hl.private_key).address.lower()
    except Exception as e:
        derived = f"<error deriving from HL_PRIVATE_KEY: {e}>"

    print("[HL] env:", CFG.hl.env)
    print("[HL] master_account:", CFG.hl.account)
    print("[HL] api_wallet_env:", CFG.hl.api_wallet)
    print("[HL] api_wallet_from_private_key:", derived)
    print("[HL] api_wallet_match:", str(derived == CFG.hl.api_wallet.lower()).lower())

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection
def get_db_connection():
    """Get database connection."""
    db_path = os.getenv("DB_PATH", "data/trades.db")
    return sqlite3.connect(db_path)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_update = 0

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except:
            self.disconnect(websocket)

    async def broadcast(self, message: str):
        # Throttle to max 1s updates
        current_time = datetime.now().timestamp()
        if current_time - self.last_update < 1.0:
            return
        
        self.last_update = current_time
        
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

# Data loading functions
def load_equity_data():
    """Load equity curve data from database or return mock."""
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("""
            SELECT timestamp, total_value FROM equity_curve 
            ORDER BY timestamp DESC 
            LIMIT 100
        """, conn)
        conn.close()
        
        if df.empty:
            logger.info("Using mock data - no equity data found")
            # Generate mock equity curve
            dates = pd.date_range(start=datetime.now() - timedelta(days=30), end=datetime.now(), freq='H')
            values = 10000 + np.cumsum(np.random.normal(0, 50, len(dates)))
            df = pd.DataFrame({'timestamp': dates, 'total_value': values})
        
        return [{"timestamp": row['timestamp'].isoformat(), "value": row['total_value']} 
                for _, row in df.iterrows()]
    except Exception as e:
        logger.error(f"Error loading equity data: {e}")
        logger.info("Using mock data - database error")
        # Mock data fallback
        dates = pd.date_range(start=datetime.now() - timedelta(days=30), end=datetime.now(), freq='H')
        values = 10000 + np.cumsum(np.random.normal(0, 50, len(dates)))
        return [{"timestamp": date.isoformat(), "value": value} 
                for date, value in zip(dates, values)]

def load_positions_data():
    """Load active positions from database or return mock."""
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("""
            SELECT * FROM trades 
            WHERE exit_px IS NULL OR exit_px = 0
            ORDER BY ts DESC 
            LIMIT 10
        """, conn)
        conn.close()
        
        if df.empty:
            logger.info("Using mock data - no active positions found")
            return [
                {"side": "long", "coin": "HYPE", "entry": 39.21, "current": 39.50, "qty": 100, 
                 "lev": 40, "sl": 38.00, "tp": 42.00, "margin": 247, "pnl": 18.4},
                {"side": "short", "coin": "BTC", "entry": 111148, "current": 110500, "qty": 0.1, 
                 "lev": 10, "sl": 112000, "tp": 109000, "margin": 1111, "pnl": 64.8}
            ]
        
        positions = []
        for _, row in df.iterrows():
            positions.append({
                "side": row.get('action', 'long'),
                "coin": row.get('asset', 'HYPE'),
                "entry": row.get('entry_px', 0),
                "current": row.get('entry_px', 0) * 1.01,  # Mock current price
                "qty": row.get('qty', 100),
                "lev": row.get('leverage', 10),
                "sl": row.get('entry_px', 0) * 0.95,  # Mock stop loss
                "tp": row.get('entry_px', 0) * 1.05,  # Mock take profit
                "margin": row.get('entry_px', 0) * row.get('qty', 100) / row.get('leverage', 10),
                "pnl": row.get('pnl_pct', 0)
            })
        return positions
    except Exception as e:
        logger.error(f"Error loading positions data: {e}")
        logger.info("Using mock data - database error")
        return [
            {"side": "long", "coin": "HYPE", "entry": 39.21, "current": 39.50, "qty": 100, 
             "lev": 40, "sl": 38.00, "tp": 42.00, "margin": 247, "pnl": 18.4}
        ]

def load_trades_data():
    """Load last 5 trades from database or return mock."""
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("""
            SELECT * FROM trades 
            WHERE exit_px IS NOT NULL AND exit_px > 0
            ORDER BY ts DESC 
            LIMIT 5
        """, conn)
        conn.close()
        
        if df.empty:
            logger.info("Using mock data - no completed trades found")
            return [
                {"side": "long", "coin": "HYPE", "entry": 39.21, "exit": 39.50, "qty": 100, 
                 "close_reason": "TP hit", "time": "10:24", "holding": "OH 19m", 
                 "notional": 3921, "fees": 1.5, "pnl": 29},
                {"side": "short", "coin": "SOL", "entry": 192.6, "exit": 190.2, "qty": 10, 
                 "close_reason": "SL hit", "time": "09:45", "holding": "OH 2h 15m", 
                 "notional": 1926, "fees": 0.8, "pnl": -24}
            ]
        
        trades = []
        for _, row in df.iterrows():
            trades.append({
                "side": row.get('action', 'long'),
                "coin": row.get('asset', 'HYPE'),
                "entry": row.get('entry_px', 0),
                "exit": row.get('exit_px', 0),
                "qty": row.get('qty', 100),
                "close_reason": "TP hit" if row.get('pnl_pct', 0) > 0 else "SL hit",
                "time": datetime.fromtimestamp(row.get('ts', 0)).strftime("%H:%M"),
                "holding": f"OH {np.random.randint(5, 120)}m",
                "notional": row.get('entry_px', 0) * row.get('qty', 100),
                "fees": abs(row.get('pnl_pct', 0)) * 0.1,
                "pnl": row.get('pnl_pct', 0)
            })
        return trades
    except Exception as e:
        logger.error(f"Error loading trades data: {e}")
        logger.info("Using mock data - database error")
        return [
            {"side": "long", "coin": "HYPE", "entry": 39.21, "exit": 39.50, "qty": 100, 
             "close_reason": "TP hit", "time": "10:24", "holding": "OH 19m", 
             "notional": 3921, "fees": 1.5, "pnl": 29}
        ]

def load_reasoning_data():
    """Load reasoning data from deepseek_thoughts or return mock."""
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("""
            SELECT * FROM deepseek_thoughts 
            ORDER BY ts DESC 
            LIMIT 10
        """, conn)
        conn.close()
        
        if df.empty:
            logger.info("Using mock data - no reasoning data found")
            return [
                {"asset": "HYPE", "time": "10:49", "signals": "RSI 25, MACD 0.15", 
                 "bias": "Bull", "recommendation": "Hold, trail SL"},
                {"asset": "BTC", "time": "10:45", "signals": "RSI 45, EMA20 up", 
                 "bias": "Neutral", "recommendation": "Wait for breakout"}
            ]
        
        reasoning = []
        for _, row in df.iterrows():
            reasoning.append({
                "asset": row.get('asset', 'HYPE'),
                "time": datetime.fromtimestamp(row.get('timestamp', 0)).strftime("%H:%M"),
                "signals": row.get('signals', 'RSI 25, MACD 0.15'),
                "bias": row.get('bias', 'Bull'),
                "recommendation": row.get('recommendation', 'Hold, trail SL')
            })
        return reasoning
    except Exception as e:
        logger.error(f"Error loading reasoning data: {e}")
        logger.info("Using mock data - database error")
        return [
            {"asset": "HYPE", "time": "10:49", "signals": "RSI 25, MACD 0.15", 
             "bias": "Bull", "recommendation": "Hold, trail SL"}
        ]

def load_prices_data():
    """Load current prices from utils or return mock."""
    try:
        # Try to import and use utils
        import sys
        sys.path.append('/app')
        from utils.indicators import AsyncIndicatorCalculator
        
        # Mock prices for now - in real implementation, fetch from Hyperliquid
        return {
            "HYPE": 39.21,
            "SOL": 192.6,
            "ETH": 3974,
            "BTC": 111148
        }
    except Exception as e:
        logger.error(f"Error loading prices data: {e}")
        logger.info("Using mock data - utils error")
        return {
            "HYPE": 39.21,
            "SOL": 192.6,
            "ETH": 3974,
            "BTC": 111148
        }

def calculate_metrics():
    """Calculate trading metrics from database or return mock."""
    try:
        conn = get_db_connection()
        df = pd.read_sql_query("""
            SELECT * FROM trades 
            ORDER BY ts DESC 
            LIMIT 100
        """, conn)
        conn.close()
        
        if df.empty:
            logger.info("Using mock data - no trades found")
            return {
                "total_value": 10000,
                "win_rate": 0.5,
                "sharpe": 0.6,
                "max_dd": -11.1,
                "trades": 7,
                "best_pnl": 19.6,
                "worst_pnl": -10
            }
        
        # Calculate real metrics
        total_value = 10000 + df['pnl_pct'].sum() if 'pnl_pct' in df.columns else 10000
        wins = df[df['pnl_pct'] > 0] if 'pnl_pct' in df.columns else pd.DataFrame()
        win_rate = len(wins) / len(df) if len(df) > 0 else 0
        
        if 'pnl_pct' in df.columns and len(df) > 1:
            returns = df['pnl_pct'].values
            sharpe = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        else:
            sharpe = 0
        
        if 'pnl_pct' in df.columns and len(df) > 1:
            cumulative = (1 + df['pnl_pct'] / 100).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            max_dd = drawdown.min() * 100
        else:
            max_dd = 0
        
        best_pnl = df['pnl_pct'].max() if 'pnl_pct' in df.columns else 19.6
        worst_pnl = df['pnl_pct'].min() if 'pnl_pct' in df.columns else -10
        
        return {
            "total_value": total_value,
            "win_rate": win_rate,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "trades": len(df),
            "best_pnl": best_pnl,
            "worst_pnl": worst_pnl
        }
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}")
        logger.info("Using mock data - database error")
        return {
            "total_value": 10000,
            "win_rate": 0.5,
            "sharpe": 0.6,
            "max_dd": -11.1,
            "trades": 7,
            "best_pnl": 19.6,
            "worst_pnl": -10
        }

# API Endpoints
@app.get("/metrics")
async def get_metrics(symbol: str = None):
    """Get trading metrics, optionally filtered by symbol."""
    return await state_service.get_metrics(symbol)

@app.get("/equity")
async def get_equity():
    """Get equity curve data."""
    return await state_service.get_equity()

@app.get("/positions")
async def get_positions(symbol: str = None):
    """Get active positions, optionally filtered by symbol."""
    return await state_service.get_positions(symbol)

@app.get("/trades")
async def get_trades(limit: int = 50, symbol: str = None):
    """Get recent trades, optionally filtered by symbol."""
    return await state_service.get_trades(limit, symbol)

@app.get("/market/snapshot")
async def get_market_snapshot(symbols: str = None):
    """Get market snapshot for symbols - cache-backed and non-blocking."""
    if not hasattr(app.state, 'market_feed') or not app.state.market_feed:
        return {"error": "stale_data", "stale_symbols": [], "reason": "market_feed_disabled"}
    
    # Parse symbols parameter
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(',')]
    else:
        symbol_list = settings.AGENT_SYMBOLS.split(',')
    
    # Get snapshots for all symbols (cache-backed, no blocking)
    snapshots = {}
    stale_symbols = []
    
    for symbol in symbol_list:
        cached_data = app.state.market_feed.get_cached(symbol)
        if not cached_data:
            return {"error": "stale_data", "stale_symbols": [symbol], "reason": "no_cached_data"}
        
        # Convert cached data to snapshot format
        snapshot = {
            "mid": cached_data.get("mid"),
            "spread_bps": cached_data.get("spread_bps"),
            "obi": cached_data.get("obi"),
            "last_update_ms": int(cached_data.get("last_tick_ts", 0) * 1000)
        }
        if snapshot.get("mid") is not None:
            snapshots[symbol] = snapshot
        else:
            snapshots[symbol] = {"meta": {"insufficient": True, "reason": "no_data"}}
            stale_symbols.append(symbol)
    
    # Return error if any symbols are stale
    if stale_symbols:
        return {
            "error": "stale_data",
            "stale_symbols": stale_symbols,
            "reason": "No cached data available"
        }
    
    return snapshots

@app.get("/agent/context")
async def get_agent_context(symbols: str = None):
    """Get agent context v2 with Lucidity feed for human-readable state."""
    from backend.util.cache import cached
    from backend.schemas.lucidity import ContextV2, LucidityFeed, AccountInfo, PositionInfo, MarketInfo, RiskInfo, OpsInfo, SimulationInfo, ReflectionInfo, DataHealthInfo, AIHealthInfo, LiveGuardInfo, WSHealthInfo
    from backend.observability.metrics import get_info_limiter_stats, get_order_limiter_stats
    
    async def get_context():
        # Get symbols (from query param or default)
        if symbols:
            symbols_list = [s.strip().upper() for s in symbols.split(',')]
        else:
            symbols_list = settings.AGENT_SYMBOLS.split(',')
        
        # Initialize stale fields tracking
        stale_fields = []
        
        # Get market data from cache
        market = {}
        market_lucidity = {}
        if hasattr(app.state, 'market_feed') and app.state.market_feed:
            for symbol in symbols_list:
                # Get microstructure data from cache
                cached_data = app.state.market_feed.get_cached(symbol)
                if cached_data:
                    micro = {
                        "mid": cached_data.get("mid"),
                        "spread_bps": cached_data.get("spread_bps"),
                        "obi": cached_data.get("obi")
                    }
                else:
                    micro = None
                if micro and micro.get("mid") is not None:
                    market[symbol] = micro
                    # Create Lucidity market info
                    market_lucidity[symbol] = MarketInfo(
                        mid=micro.get("mid"),
                        spread_bps=micro.get("spread_bps"),
                        obi=micro.get("obi"),
                        rtn_5s=None,  # Not available in cached data
                        funding_rate=None,  # TODO: Get from HL API
                        open_interest=None,  # TODO: Get from HL API
                        last_update_ms=int(time.time() * 1000)
                    )
                else:
                    # No cached data for this symbol
                    stale_fields.append(f"market.{symbol}")
                    # Create empty market info
                    market_lucidity[symbol] = MarketInfo(
                        mid=None,
                        spread_bps=None,
                        obi=None,
                        rtn_5s=None,
                        funding_rate=None,
                        open_interest=None,
                        last_update_ms=int(time.time() * 1000)
                    )
        
        # Get account data from state service with timeout
        portfolio_data = {}
        positions_data = []
        
        try:
            # Try to get fresh data with timeout
            if await get_info_limiter().acquire(timeout_ms=100):
                portfolio_data = await state_service.get_metrics()
                positions_data = await state_service.get_positions()
            else:
                logger.warning("Rate limiter timeout, using stale account data")
                stale_fields.extend(["account.equity", "account.positions"])
        except Exception as e:
            logger.warning(f"Failed to get account data: {e}")
            stale_fields.extend(["account.equity", "account.positions"])
        
        # Build account info
        total_value = portfolio_data.get("total_value", 0) if isinstance(portfolio_data, dict) else 0
        account_info = AccountInfo(
            equity=total_value,
            margin_ratio=0.0,  # TODO: Calculate from positions
            collateral_health="healthy",  # TODO: Calculate based on margin
            liquidation_buffer=total_value * 0.1,  # Estimate 10% buffer
            free_collateral=total_value * 0.9,  # Estimate 90% free
            total_value=total_value,
            maintenance_margin=total_value * 0.05  # Estimate 5% maintenance
        )
        
        # Build positions info
        positions_lucidity = []
        for pos in positions_data:
            if isinstance(pos, dict):
                positions_lucidity.append(PositionInfo(
                    symbol=pos.get("coin", "UNKNOWN"),
                    size=pos.get("qty", 0),
                    avg_px=pos.get("entry", 0),
                    upnl=pos.get("pnl", 0),
                    delta=0.0,  # TODO: Calculate vs target
                    leverage_est=pos.get("lev", 1),
                    side=pos.get("side", "long"),
                    notional=pos.get("qty", 0) * pos.get("entry", 0),
                    margin_used=pos.get("margin", 0)
                ))
        
        # Build risk info with budget guard
        from backend.util.budget_guard import get_status as get_budget_status
        budget_status = get_budget_status()
        
        risk_info = RiskInfo(
            max_notional_usd=settings.HL_MAX_NOTIONAL_USD,
            cross_bps_cap=settings.HL_MAX_CROSS_BPS,
            trading_enabled=settings.HL_TRADING_ENABLED,
            kill_switch=True,  # TODO: Get from actual kill switch
            position_risk_pct=settings.AGENT_POSITION_RISK_PCT,
            daily_dd_limit=settings.AGENT_MAX_DRAWDOWN_PCT,
            budget_drawdown_pct=budget_status.get("drawdown_pct", 0.0),
            budget_guard_triggered=budget_status.get("triggered", False)
        )
        
        # Build ops info
        info_stats = get_info_limiter_stats()
        order_stats = get_order_limiter_stats()
        
        # Update stats with current limiter state
        try:
            from backend.util.ratelimit import get_info_limiter, get_order_limiter
            info_limiter = get_info_limiter()
            order_limiter = get_order_limiter()
            
            info_stats.rps = info_limiter.rps
            info_stats.burst = info_limiter.burst
            info_stats.tokens = info_limiter.tokens
            
            order_stats.rps = order_limiter.rps
            order_stats.burst = order_limiter.burst
            order_stats.tokens = order_limiter.tokens
        except Exception as e:
            logger.warning(f"Failed to update limiter stats: {e}")
        
        # Build data health info
        data_health_info = None
        try:
            from backend.services.market_sampler import get_sampler
            sampler = get_sampler()
            if sampler:
                health_metrics = sampler.get_health_metrics()
                data_health_info = DataHealthInfo(
                    status=health_metrics.get("status", "unknown"),
                    mids_nonnull_pct=health_metrics.get("mids_nonnull_pct", {}),
                    avg_last_msg_ms_ago=health_metrics.get("avg_last_msg_ms_ago", {})
                )
        except Exception as e:
            logger.warning(f"Failed to get data health: {e}")
        
        # Build AI health info
        ai_health_info = None
        try:
            from backend.observability.ai_health import get_ai_health_metrics
            ai_metrics = get_ai_health_metrics()
            ai_health_info = AIHealthInfo(
                parse_success_1h=ai_metrics.get("parse_success_1h", 1.0),
                reprompt_rate=ai_metrics.get("reprompt_rate", 0.0),
                mode=ai_metrics.get("mode", "sim")
            )
        except Exception as e:
            logger.warning(f"Failed to get AI health: {e}")
        
        # Build live guard info
        live_guard_info = None
        try:
            from backend.util.live_guard import get_live_guard_status
            guard_status = get_live_guard_status()
            live_guard_info = LiveGuardInfo(
                active=guard_status.get("active", False),
                mode=guard_status.get("mode", "sim"),
                reason=guard_status.get("reason", "unknown")
            )
        except Exception as e:
            logger.warning(f"Failed to get live guard: {e}")
            live_guard_info = None
        
        # Build WebSocket health info
        ws_health_info = None
        try:
            if hasattr(app.state, 'market_feed') and app.state.market_feed:
                health_metrics = app.state.market_feed.get_health_metrics()
                ws_health_info = WSHealthInfo(
                    connected=health_metrics.get("connected", False),
                    last_tick_s_ago=health_metrics.get("last_tick_s_ago", 999.0),
                    symbols_active=health_metrics.get("symbols_active", 0),
                    reconnects=health_metrics.get("reconnects", 0),
                    total_ticks=health_metrics.get("total_ticks", 0),
                    error_count=health_metrics.get("error_count", 0)
                )
        except Exception as e:
            logger.warning(f"Failed to get WebSocket health: {e}")
        
        # Get WebSocket state (no awaits)
        ws_connected = False
        last_msg_ms_ago = None
        reconnects = 0
        backoff_ms = None
        lag_ms = 0
        
        if hasattr(app.state, 'market_feed') and app.state.market_feed:
            ws_connected = app.state.market_feed.is_connected()
            reconnects = app.state.market_feed.get_reconnect_count()
            last_tick_s_ago = app.state.market_feed.last_tick_s_ago()
            last_msg_ms_ago = int(last_tick_s_ago * 1000) if last_tick_s_ago < 999 else None
        
        ops_info = OpsInfo(
            info_limiter=info_stats.to_dict(),
            order_limiter=order_stats.to_dict(),
            ws_connected=ws_connected,
            last_msg_ms_ago=last_msg_ms_ago,
            reconnects=reconnects,
            backoff_ms=backoff_ms,
            lag_ms=lag_ms,
            stale=len(stale_fields) > 0,
            stale_fields=stale_fields,
            data_health=data_health_info,
            ai_health=ai_health_info,
            live_guard=live_guard_info,
            ws_health=ws_health_info
        )
        
        # Build simulation info
        from backend.services.sim_broker import get_sim_broker
        from backend.ai.reflection import get_reflection_stats, check_and_generate_reflection
        sim_broker = get_sim_broker()
        sim_metrics = sim_broker.get_metrics()
        
        # Check if reflection should be generated
        reflection_generated = check_and_generate_reflection()
        
        simulation_info = SimulationInfo(
            trades=sim_metrics["trades"],
            win_rate=sim_metrics["win_rate"],
            realized_pnl_usd=sim_metrics["realized_pnl_usd"],
            unrealized_pnl_usd=sim_metrics["unrealized_pnl_usd"],
            avg_slippage_bps=sim_metrics["avg_slippage_bps"]
        )
        
        # Build reflection info
        reflection_stats = get_reflection_stats()
        reflection_info = ReflectionInfo(
            win_rate=reflection_stats["win_rate"],
            pnl_10_usd=reflection_stats["pnl_10_usd"],
            policy_score=reflection_stats["policy_score"],
            updated_at=reflection_stats["updated_at"]
        )
        
        # Build Lucidity feed
        lucidity = LucidityFeed(
            account=account_info,
            positions=positions_lucidity,
            market=market_lucidity,
            risk=risk_info,
            ops=ops_info,
            meta={
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "version": "v2"
            },
            simulation=simulation_info,
            reflection=reflection_info
        )
        
        # Legacy account and limits for backward compatibility
        account = {
            "equity": total_value,
            "free_collateral": total_value * 0.9,
            "positions": positions_data,
            "liq_distance": total_value * 0.1
        }
        
        limits = {
            "max_notional_usd": settings.HL_MAX_NOTIONAL_USD,
            "max_cross_bps": settings.HL_MAX_CROSS_BPS,
            "trading_enabled": settings.HL_TRADING_ENABLED,
            "kill_switch": True
        }
        
        # Check for insufficient data
        insufficient = []
        if not market:
            insufficient.append("market_feed")
        
        return ContextV2(
            symbols=symbols_list,
            market=market,
            account=account,
            limits=limits,
            lucidity=lucidity,
            meta={
                "ts": int(time.time() * 1000),
                "cache_ms": 800,
                "insufficient": insufficient,
                "version": "v2",
                "generated_at": datetime.now().isoformat()
            }
        )
    
    async def producer():
        return await get_context()
    
    return await cached("agent_context", 800, producer)

@app.get("/signer_check")
def signer_check():
    """Verify API wallet identity."""
    CFG = load_config()
    result = {
        "env": CFG.hl.env,
        "master_account": CFG.hl.account,
        "api_wallet_env": CFG.hl.api_wallet,
        "api_wallet_from_private_key": None,
        "match": None,
    }
    try:
        derived = Account.from_key(CFG.hl.private_key).address.lower()
        result["api_wallet_from_private_key"] = derived
        result["match"] = (derived == CFG.hl.api_wallet.lower())
    except Exception as e:
        result["api_wallet_from_private_key"] = f"<derive_error: {e}>"
        result["match"] = False
    return result

@app.get("/whoami_trade")
def whoami_trade():
    """Show the signer the trade path will use."""
    CFG = load_config()
    signer_from_key = Account.from_key(CFG.hl.private_key).address.lower()
    return {
        "env": CFG.hl.env,
        "master_account": CFG.hl.account,
        "api_wallet_env": CFG.hl.api_wallet,
        "api_wallet_from_private_key": signer_from_key,
        "match": signer_from_key == CFG.hl.api_wallet.lower(),
    }

@app.get("/agent_status")
async def agent_status():
    """Verify API wallet approval for master account."""
    CFG = load_config()
    
    master = CFG.hl.account.lower()
    apiw = CFG.hl.api_wallet.lower()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # ✅ Correct query type for Hyperliquid agent list
            resp = await client.post(
                f"{CFG.hl.rest_url}/info",
                headers={"Content-Type": "application/json"},
                json={"type": "extraAgents", "user": master},
            )
            resp.raise_for_status()
            data = resp.json() or []
            
            # Expected structure: [{"name":"my_api_wallet","address":"0x...","validUntil":"..."}, ...]
            addrs = {a.get("address", "").lower() for a in data if isinstance(a, dict)}
            approved = apiw in addrs
            
            return {
                "env": CFG.hl.env,
                "master": master,
                "api_wallet": apiw,
                "approved": approved,
                "agents": data
            }
    except httpx.HTTPStatusError as e:
        return {
            "env": CFG.hl.env,
            "master": master,
            "api_wallet": apiw,
            "approved": False,
            "error": f"HTTP {e.response.status_code}: {e.response.text}"
        }
    except Exception as e:
        return {
            "env": CFG.hl.env,
            "master": master,
            "api_wallet": apiw,
            "approved": False,
            "error": str(e)
        }


@app.post("/signing_parity")
def signing_parity():
    """Test signer recovery from the exact same preimage used by SDK."""
    CFG = load_config()
    action = {"type":"order","orders":[{"a":0,"b":True,"p":"1","s":"0.0001","r":True,"t":{"limit":{"tif":"Ioc"}}}],"grouping":"na"}
    nonce = int(time.time()*1000)

    # Call the executor helper but DO NOT actually post
    ex = OrderExecutor(CFG.hl.account, CFG.hl.private_key, CFG.hl.rest_url)
    sig, body_str, envelope = ex._sdk_sign_order(action, nonce)

    # Locally recover signer from the preimage
    preimage = json.dumps({"action": action, "nonce": nonce}, separators=(",", ":"), ensure_ascii=False).encode()
    msg_hash = keccak(preimage)
    v = sig["v"]; r = int(sig["r"],16); s = int(sig["s"],16)
    # Normalize v value (27/28 -> 0/1)
    v_normalized = v - 27 if v >= 27 else v
    pub = keys.Signature(vrs=(v_normalized,r,s)).recover_public_key_from_msg_hash(msg_hash)
    recovered = pub.to_checksum_address().lower()

    return {
        "api_wallet_env": CFG.hl.api_wallet,
        "api_wallet_from_key": Account.from_key(CFG.hl.private_key).address.lower(),
        "recovered_from_preimage": recovered,
        "match": recovered == CFG.hl.api_wallet,
        "body_str": body_str,  # for inspection
    }

@app.get("/reasoning")
async def get_reasoning():
    """Get reasoning data."""
    return load_reasoning_data()  # Keep old function for now

@app.get("/prices")
async def get_prices():
    """Get current prices."""
    return load_prices_data()  # Keep old function for now

@app.get("/config-check")
def config_check():
    """Check configuration without exposing secrets."""
    return {"ok": True, "config": redacted(CFG)}

@app.get("/status")
def status():
    """Get system health status - non-blocking, in-process only."""
    import os
    import psutil
    
    # Get process info
    pid = os.getpid()
    process = psutil.Process(pid)
    uptime_s = time.time() - process.create_time()
    
    # Get basic system info without any external calls
    return {
        "uptime_s": round(uptime_s, 1),
        "pid": pid,
        "version": "v2",
        "now": int(time.time() * 1000),
        "healthy": True,
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
        "cpu_percent": round(process.cpu_percent(), 1)
    }

@app.get("/debug_book")
def debug_book(symbol: str = "BTC"):
    """Debug endpoint to test bid/ask price fetching."""
    from common.config import load_config
    from bot.executor import OrderExecutor
    cfg = load_config()
    exe = OrderExecutor(cfg.hl.account, cfg.hl.private_key, base_url=cfg.hl.rest_url)

    try:
        bid, ask = exe._best_book(symbol)
        return {"symbol": symbol, "bid": bid, "ask": ask}
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

@app.get("/l1_shape_probe")
def l1_shape_probe(symbol: str = "BTC", usd: float = 12.0):
    """Probe both L1 layouts (action-first vs nonce-first) to determine canonical format."""
    import asyncio
    import hashlib
    import msgpack
    from hexbytes import HexBytes
    from eth_keys import keys
    from common.hl_meta import get_asset_id
    from common.hl_signing import build_short_action
    
    CFG = load_config()
    
    async def probe_layout(envelope, label):
        """Test a specific layout and return results."""
        try:
            # Msgpack with exact options
            packed = msgpack.packb(envelope, use_bin_type=False, strict_types=True)
            digest = hashlib.sha256(packed).digest()
            digest_hex = "0x" + digest.hex()
            
            # Sign with eth_keys
            sk = keys.PrivateKey(HexBytes(CFG.hl.private_key))
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
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{CFG.hl.rest_url}/exchange", json=final_envelope)
                body = resp.text
                
            # Parse server error address
            server_err_addr = None
            if "User or API Wallet" in body:
                import re
                match = re.search(r"User or API Wallet (0x[a-fA-F0-9]{40}) does not exist", body)
                if match:
                    server_err_addr = match.group(1).lower()
            
            logger.info(f"[HL:probe:{label}] packed_hex={packed.hex()[:200]}")
            logger.info(f"[HL:probe:{label}] digest={digest_hex}")
            logger.info(f"[HL:probe:{label}] local_recovered={local_recovered}")
            logger.info(f"[HL:probe:{label}] server_err_addr={server_err_addr}")
            logger.info(f"[HL:probe:{label}] http_status={resp.status_code}")
            logger.info(f"[HL:probe:{label}] body={body[:200]}")
            
            return {
                "label": label,
                "packed_hex": packed.hex()[:200],
                "digest_hex": digest_hex,
                "local_recovered": local_recovered,
                "server_err_addr": server_err_addr,
                "http_status": resp.status_code,
                "body": body[:500],
                "match_local": local_recovered == CFG.hl.api_wallet.lower(),
                "match_server": server_err_addr == CFG.hl.api_wallet.lower() if server_err_addr else False
            }
            
        except Exception as e:
            logger.error(f"[HL:probe:{label}] error: {e}")
            return {
                "label": label,
                "error": str(e),
                "match_local": False,
                "match_server": False
            }
    
    async def run_probe():
        # Get asset ID
        asset_id = await get_asset_id(symbol, CFG.hl.rest_url)
        
        # Build short-form action
        action = build_short_action(
            asset_id=int(asset_id),
            is_buy=True,
            sz_str="0.0001",  # Small size for testing
            px_str=None,  # Market-style IOC
            tif="Ioc",
            reduce_only=False,
            grouping="na"
        )
        
        nonce = int(time.time() * 1000)
        
        # Layout A: action-first
        envelope_a = {"action": action, "nonce": nonce}
        result_a = await probe_layout(envelope_a, "action-first")
        
        # Layout B: nonce-first  
        envelope_b = {"nonce": nonce, "action": action}
        result_b = await probe_layout(envelope_b, "nonce-first")
        
        return {
            "symbol": symbol,
            "usd": usd,
            "agent": CFG.hl.api_wallet.lower(),
            "master": CFG.hl.account.lower(),
            "layout_a": result_a,
            "layout_b": result_b,
            "summary": {
                "layout_a_works": result_a.get("match_server", False),
                "layout_b_works": result_b.get("match_server", False),
                "recommended_layout": "action-first" if result_a.get("match_server", False) else "nonce-first" if result_b.get("match_server", False) else "neither"
            }
        }
    
    return asyncio.run(run_probe())

@app.post("/trade_test")
def trade_test(
    symbol: str = Query("BTC"),
    side: str = Query("LONG"),
    usd: float = Query(10.0),
    hold_seconds: float = Query(3.0),
    dry_run: bool = Query(True),
):
    """One-shot live trade test using clean SDK implementation."""
    CFG = load_config()
    
    # Guard: Check API wallet match
    try:
        derived = Account.from_key(CFG.hl.private_key).address.lower()
        if derived != CFG.hl.api_wallet.lower():
            return {"error": "API wallet mismatch: private key does not derive to HL_API_WALLET_ADDRESS"}
    except Exception as e:
        return {"error": f"Failed to derive address from private key: {e}"}
    
    # Guard: Check agent approval (quick check)
    try:
        # This is a simplified check - in production you might want to cache this
        import httpx
        with httpx.Client() as client:
            resp = client.get("http://localhost:8000/agent_status", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("approved", False):
                    return {"error": "Agent not approved. Please approve the API wallet in Hyperliquid UI."}
    except Exception as e:
        logger.warning(f"Could not verify agent approval: {e}")
    
    try:
        # Create executor with clean SDK configuration
        # Pass master account as account_address, API wallet private key as signer_private_key
        exe = OrderExecutor(
            account_address=CFG.hl.account,          # master (funded) account
            signer_private_key=CFG.hl.private_key,   # API wallet private key
            base_url=CFG.hl.rest_url
        )

        if dry_run:
            return {"mode": "DRY_RUN", "symbol": symbol, "side": side, "usd": usd, "note": "Would place IOC enter+exit"}

        is_buy = side.upper() == "LONG"

        enter = asyncio.run(exe.place_order(symbol, usd, is_buy=is_buy))
        time.sleep(hold_seconds)
        exit_resp = asyncio.run(exe.place_reduce_only(symbol, usd, side_long=is_buy))
        
        # Ensure enter and exit_resp are dictionaries
        if not isinstance(enter, dict):
            enter = {"oid": enter if isinstance(enter, int) else None, "raw": enter}
        if not isinstance(exit_resp, dict):
            exit_resp = {"oid": exit_resp if isinstance(exit_resp, int) else None, "raw": exit_resp}

        # Surface rejected reason if present
        def reject_reason(raw):
            try:
                statuses = (raw or {}).get("response", {}).get("data", {}).get("statuses", [])
                if statuses and isinstance(statuses[0], dict) and "rejected" in statuses[0]:
                    return statuses[0]["rejected"].get("reason")
            except Exception:
                pass
            return None

        return {
            "mode": "LIVE",
            "enter_oid": enter.get("oid"),
            "exit_oid": exit_resp.get("oid"),
            "enter_reject": reject_reason(enter.get("raw")),
            "exit_reject": reject_reason(exit_resp.get("raw")),
            "enter_raw_type": type(enter.get("raw")).__name__,
            "exit_raw_type": type(exit_resp.get("raw")).__name__,
            "enter_raw": enter.get("raw"),
            "exit_raw": exit_resp.get("raw"),
        }
        
    except Exception as e:
        logger.error(f"Trade test failed: {e}")
        return {"error": str(e), "success": False}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Send updates every 1s (throttled)
            await asyncio.sleep(1)
            
            # Get latest data using state service
            metrics = await state_service.get_metrics()
            equity = await state_service.get_equity()
            positions = await state_service.get_positions()
            trades = await state_service.get_trades()
            reasoning = load_reasoning_data()  # Keep old function for now
            prices = load_prices_data()  # Keep old function for now
            
            # Send to client
            update_data = {
                "type": "update",
                "metrics": metrics,
                "equity": equity[-10:],  # Last 10 points for performance
                "positions": positions,
                "trades": trades,
                "reasoning": reasoning,
                "prices": prices,
                "timestamp": datetime.now().isoformat()
            }
            
            await manager.send_personal_message(
                json.dumps(update_data),
                websocket
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Mount static files at the end to avoid conflicts with API routes
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
