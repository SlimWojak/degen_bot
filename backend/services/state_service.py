"""
State service for live Hyperliquid data integration.
Provides cached access to portfolio, positions, trades, and metrics.
"""

import asyncio
import time
import sqlite3
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging
from contextlib import suppress

from backend.config import settings
from backend.util.cache import cached
from backend.util.ratelimit import initialize_limiters, get_info_limiter, get_order_limiter
from backend.services.mock_state import MockStateService
from common.hl_client import connect, discover_price, quantize_px, quantize_size

logger = logging.getLogger(__name__)

class StateService:
    """Service for managing live Hyperliquid state data."""
    
    def __init__(self):
        self.cache_ttl = settings.STATE_CACHE_MS
        self.data_source = settings.DATA_SOURCE
        self.default_symbol = settings.HL_DEFAULT_SYMBOL
        
        # Initialize rate limiters
        initialize_limiters(
            info_rps=settings.HL_RATE_INFO_RPS,
            order_rps=settings.HL_RATE_ORDER_RPS,
            burst=settings.HL_RATE_BURST
        )
        
        # L2 cooldown tracking per symbol
        self.last_l2_ts: Dict[str, float] = {}
        self.l2_cooldown_ms = settings.HL_L2_COOLDOWN_MS
        
        # In-flight request deduplication
        self.inflight_requests: Dict[str, asyncio.Future] = {}
    
    async def _timeboxed(self, coro, ms: int):
        """Timebox a coroutine with the given timeout in milliseconds."""
        try:
            return await asyncio.wait_for(coro, timeout=ms/1000)
        except Exception:
            return None
    
    async def _rate_limited_hl_call(self, method_name: str, coro, timeout_ms: int = 1000):
        """
        Make a rate-limited HL API call with deduplication.
        
        Args:
            method_name: Name of the method for deduplication key
            coro: Coroutine to execute
            timeout_ms: Timeout in milliseconds
            
        Returns:
            Result of the coroutine or None if failed
        """
        # Create deduplication key
        key = f"{method_name}_{id(coro)}"
        
        # Check if request is already in flight
        if key in self.inflight_requests:
            logger.debug(f"Request {method_name} already in flight, awaiting existing future")
            try:
                return await self.inflight_requests[key]
                return None
            except Exception as e:
                logger.warning(f"Existing request {method_name} failed: {e}")
                # Remove failed future and continue with new request
                self.inflight_requests.pop(key, None)
        
        # Create new future for this request
        future = asyncio.Future()
        self.inflight_requests[key] = future
        
        try:
            # Check circuit breaker
            from backend.util.breakers import should_skip, record_success, record_failure
            
            if should_skip("info"):
                logger.warning(f"Circuit breaker active for info, skipping {method_name}")
                future.set_result(None)
                return None
            
            # Acquire rate limiter token
            await get_info_limiter().acquire()
            
            # Execute the call with timeout
            result = await self._timeboxed(coro, timeout_ms)
            
            # Record success for circuit breaker
            record_success("info")
            
            # Set result and clean up
            future.set_result(result)
            return result
            
        except Exception as e:
            logger.error(f"Rate-limited HL call {method_name} failed: {e}")
            # Record failure for circuit breaker
            record_failure("info")
            future.set_exception(e)
            return None
        finally:
            # Clean up future
            self.inflight_requests.pop(key, None)
    
    async def _check_l2_cooldown(self, symbol: str) -> bool:
        """
        Check if L2 snapshot is in cooldown for the given symbol.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if in cooldown, False if can proceed
        """
        now = time.time() * 1000  # Convert to milliseconds
        last_ts = self.last_l2_ts.get(symbol, 0)
        
        if now - last_ts < self.l2_cooldown_ms:
            logger.debug(f"L2 cooldown active for {symbol}: {now - last_ts:.1f}ms < {self.l2_cooldown_ms}ms")
            return True
        
        # Update timestamp
        self.last_l2_ts[symbol] = now
        return False
    
    async def _get_hl_clients(self):
        """Get HL clients for health checks."""
        return connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
    
    async def check_market_fast(self, symbol: str) -> bool:
        """Fast market check with timeout, never raises, always returns bool."""
        with suppress(Exception):
            price = await self._timeboxed(discover_price(None, symbol), settings.STATUS_TIMEOUT_MS)
            return bool(price and float(price) > 0)
        return False
    
    async def check_api_fast(self) -> bool:
        """Fast API check using cached state only, never makes remote calls."""
        try:
            # Check cached timestamps and error counts only
            now = time.time()
            
            # Check if we have recent successful API calls
            last_success = getattr(self, '_last_api_success', 0)
            if now - last_success < 300:  # 5 minutes
                return True
            
            # Check error count
            error_count = getattr(self, '_api_error_count', 0)
            if error_count > 10:  # Too many recent errors
                return False
            
            # Default to healthy if no recent data
            return True
            
        except Exception:
            return False
    
    async def db_health(self) -> str:
        """Check database health, returns 'synced' or 'stale'."""
        try:
            last_trade_time = await self._get_last_trade_time()
            if last_trade_time:
                age_seconds = time.time() - last_trade_time
                return "synced" if age_seconds < 60 else "stale"
            return "stale"
        except Exception:
            return "stale"
    
    async def ws_health(self) -> str:
        """Check WebSocket health, returns 'connected' or 'disconnected'."""
        # For now, always return disconnected since we don't have persistent WS tracking
        return "disconnected"
        
    async def get_metrics(self, symbol: str = None) -> Dict[str, Any]:
        """Get portfolio metrics from live or mock data, optionally filtered by symbol."""
        if self.data_source == "mock":
            return MockStateService.get_metrics(symbol)
        
        async def get_metrics_producer():
            return await self._get_live_metrics()
        
        return await cached(
            "metrics",
            self.cache_ttl,
            get_metrics_producer
        )
    
    async def get_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get active positions from live or mock data, optionally filtered by symbol."""
        if self.data_source == "mock":
            return MockStateService.get_positions(symbol)
        
        async def get_positions_producer():
            return await self._get_live_positions()
        
        return await cached(
            "positions", 
            self.cache_ttl,
            get_positions_producer
        )
    
    async def get_trades(self, limit: int = 50, symbol: str = None) -> List[Dict[str, Any]]:
        """Get recent trades from live or mock data, optionally filtered by symbol."""
        if self.data_source == "mock":
            return MockStateService.get_trades(limit, symbol)
        
        async def get_trades_producer():
            return await self._get_live_trades(limit)
        
        return await cached(
            f"trades_{limit}",
            self.cache_ttl,
            get_trades_producer
        )
    
    async def get_equity(self) -> List[Dict[str, Any]]:
        """Get equity curve from live or mock data."""
        if self.data_source == "mock":
            return MockStateService.get_equity()
        
        async def get_equity_producer():
            return await self._get_live_equity()
        
        return await cached(
            "equity",
            self.cache_ttl,
            get_equity_producer
        )
    
    async def get_status(self) -> Dict[str, str]:
        """Get system health status with concurrent, time-boxed checks."""
        if self.data_source == "mock":
            return MockStateService.get_status()
        
        # Run checks concurrently with timeouts
        start_time = time.time()
        
        # Concurrent checks
        market_ok_coro = self.check_market_fast(self.default_symbol)
        api_ok_coro = self.check_api_fast()
        db_state_coro = self.db_health()
        ws_state_coro = self.ws_health()
        
        try:
            # Wait for all checks with total timeout
            market_ok, api_ok, db_state, ws_state = await asyncio.wait_for(
                asyncio.gather(
                    market_ok_coro, 
                    api_ok_coro, 
                    db_state_coro, 
                    ws_state_coro,
                    return_exceptions=True
                ),
                timeout=settings.STATUS_TOTAL_TIMEOUT_MS/1000
            )
        except Exception:
            # If total timeout exceeded, use defaults
            market_ok, api_ok, db_state, ws_state = False, False, "stale", "disconnected"
        
        # Handle exceptions from individual checks
        if isinstance(market_ok, Exception):
            market_ok = False
        if isinstance(api_ok, Exception):
            api_ok = False
        if isinstance(db_state, Exception):
            db_state = "stale"
        if isinstance(ws_state, Exception):
            ws_state = "disconnected"
        
        # Bot status logic
        bot_status = "error"
        if self.data_source == "live" and market_ok and api_ok and settings.HL_TRADING_ENABLED:
            bot_status = "ok"
        elif self.data_source == "mock":
            bot_status = "mock"
        
        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(f"Status check completed in {elapsed_ms:.1f}ms")
        
        # Get symbols from config
        symbols = settings.AGENT_SYMBOLS.split(',') if hasattr(settings, 'AGENT_SYMBOLS') else ['BTC', 'ETH', 'SOL']
        
        return {
            "market": "ok" if market_ok else "error",
            "api": "healthy" if api_ok else "error", 
            "db": db_state,
            "ws": ws_state,
            "bot": bot_status,
            "_meta": {
                "source": self.data_source,
                "symbols": symbols
            }
        }
    
    async def check_market(self, symbol: str) -> bool:
        """Check market health with 400ms timeout, return bool (no exceptions)."""
        try:
            price = await asyncio.wait_for(
                self._test_price_discovery(), 
                timeout=0.4
            )
            return price is not None and price > 0
        except Exception as e:
            logger.debug(f"Market check failed: {e}")
            return False
    
    async def check_api(self) -> bool:
        """Check API health with 400ms timeout, return bool (no exceptions)."""
        try:
            await asyncio.wait_for(
                self._test_exchange_connection(),
                timeout=0.4
            )
            return True
        except Exception as e:
            logger.debug(f"API check failed: {e}")
            return False
    
    # Mock data methods moved to backend/services/mock_state.py
    
    # Live data methods
    async def _get_live_metrics(self) -> Dict[str, Any]:
        """Get metrics from live Hyperliquid data."""
        try:
            # Use custom signer if specified
            if settings.HL_SIGNER_IMPL == "custom":
                logger.info("Using custom signer implementation")
            else:
                logger.info("Using SDK signer implementation")
            
            exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
            user = settings.HL_ACCOUNT_ADDRESS
            
            # Get portfolio data (rate limited)
            portfolio = await self._rate_limited_hl_call(
                "portfolio", 
                asyncio.to_thread(lambda: info.portfolio(user))
            )
            if not portfolio or not isinstance(portfolio, dict):
                return {"_meta": {"insufficient": True, "reason": "No portfolio data"}}
            
            # Get user fills for trade analysis (rate limited)
            fills = await self._rate_limited_hl_call(
                "user_fills",
                asyncio.to_thread(lambda: info.user_fills(user))
            )
            if not fills or not isinstance(fills, list):
                return {"_meta": {"insufficient": True, "reason": "No trade history"}}
            
            # Calculate metrics from fills
            total_trades = len(fills)
            winning_trades = sum(1 for fill in fills if isinstance(fill, dict) and fill.get("pnl", 0) > 0)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0
            
            # Calculate P&L metrics
            pnls = [fill.get("pnl", 0) for fill in fills if isinstance(fill, dict) and fill.get("pnl") is not None]
            if pnls:
                best_pnl = max(pnls)
                worst_pnl = min(pnls)
                total_pnl = sum(pnls)
            else:
                best_pnl = worst_pnl = total_pnl = 0
            
            # Simple Sharpe calculation (daily returns)
            if len(pnls) > 1:
                daily_returns = [pnls[i] - pnls[i-1] for i in range(1, len(pnls))]
                if daily_returns:
                    mean_return = sum(daily_returns) / len(daily_returns)
                    variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
                    sharpe = mean_return / (variance ** 0.5) if variance > 0 else 0
                else:
                    sharpe = 0
            else:
                sharpe = 0
            
            # Max drawdown calculation
            max_dd = 0
            peak = 0
            running_total = 0
            for pnl in pnls:
                running_total += pnl
                if running_total > peak:
                    peak = running_total
                drawdown = peak - running_total
                if drawdown > max_dd:
                    max_dd = drawdown
            
            return {
                "total_value": portfolio.get("totalValue", 0),
                "win_rate": win_rate,
                "sharpe": sharpe,
                "max_dd": -max_dd,  # Negative for display
                "trades": total_trades,
                "best_pnl": best_pnl,
                "worst_pnl": worst_pnl,
                "_meta": {"source": "live"}
            }
            
        except Exception as e:
            logger.error(f"Error getting live metrics: {e}")
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Structured JSON log for monitoring
            logger.error(f"HL_METRICS_ERROR: {{'error': '{str(e)}', 'type': '{type(e).__name__}', 'user': '{user}', 'network': '{settings.HL_NETWORK}', 'signer_impl': '{settings.HL_SIGNER_IMPL}'}}")
            return {"_meta": {"error": str(e), "insufficient": True}}
    
    async def _get_live_positions(self) -> List[Dict[str, Any]]:
        """Get positions from live Hyperliquid data."""
        try:
            exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
            user = settings.HL_ACCOUNT_ADDRESS
            
            # Get portfolio data (rate limited)
            portfolio = await self._rate_limited_hl_call(
                "portfolio_positions",
                asyncio.to_thread(lambda: info.portfolio(user))
            )
            if not portfolio:
                return []
            
            positions = []
            asset_positions = portfolio.get("assetPositions", [])
            
            for pos in asset_positions:
                if pos.get("position", {}).get("szi", 0) == 0:
                    continue  # Skip zero positions
                
                position = pos.get("position", {})
                coin = pos.get("coin", "UNKNOWN")
                szi = float(position.get("szi", 0))
                entry_px = float(position.get("entryPx", 0))
                
                # Get current price
                try:
                    current_px = float(position.get("positionValue", 0)) / abs(szi) if szi != 0 else 0
                except:
                    current_px = entry_px
                
                # Calculate P&L
                unrealized_pnl = float(position.get("unrealizedPnl", 0))
                
                positions.append({
                    "side": "long" if szi > 0 else "short",
                    "coin": coin,
                    "entry": quantize_px(info, coin, entry_px),
                    "current": quantize_px(info, coin, current_px),
                    "qty": abs(szi),
                    "lev": 1,  # Default leverage
                    "sl": 0,   # Not available in portfolio data
                    "tp": 0,   # Not available in portfolio data
                    "margin": abs(szi) * entry_px,  # Approximate
                    "pnl": unrealized_pnl,
                    "_meta": {"source": "live"}
                })
            
            return positions
            
        except Exception as e:
            logger.error(f"Error getting live positions: {e}")
            return []
    
    async def _get_live_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get trades from live Hyperliquid data."""
        try:
            exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
            user = settings.HL_ACCOUNT_ADDRESS
            
            # Get user fills (rate limited)
            fills = await self._rate_limited_hl_call(
                "user_fills_trades",
                asyncio.to_thread(lambda: info.user_fills(user))
            )
            if not fills or not isinstance(fills, list):
                # Fallback to SQLite trades
                return await self._get_sqlite_trades(limit)
            
            # Convert fills to trade format
            trades = []
            for fill in fills[-limit:]:  # Get last N fills
                coin = fill.get("coin", "UNKNOWN")
                is_buy = fill.get("isBuy", True)
                px = float(fill.get("px", 0))
                sz = float(fill.get("sz", 0))
                pnl = float(fill.get("pnl", 0))
                time_ms = fill.get("time", 0)
                
                # Format time
                trade_time = datetime.fromtimestamp(time_ms / 1000).strftime("%H:%M")
                
                trades.append({
                    "side": "long" if is_buy else "short",
                    "coin": coin,
                    "entry": quantize_px(info, coin, px),
                    "exit": quantize_px(info, coin, px),  # Same for fills
                    "qty": quantize_size(info, coin, sz),
                    "close_reason": "Fill",
                    "time": trade_time,
                    "holding": "N/A",
                    "notional": px * sz,
                    "fees": 0,  # Not available in fills
                    "pnl": pnl,
                    "_meta": {"source": "live"}
                })
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting live trades: {e}")
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Fallback to SQLite
            return await self._get_sqlite_trades(limit)
    
    async def _get_sqlite_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get trades from SQLite database as fallback."""
        try:
            conn = sqlite3.connect("data/trades.db")
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT asset, action, entry_px, exit_px, size_usd, pnl_usd, ts, reason
                FROM trades 
                ORDER BY ts DESC 
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            trades = []
            for row in rows:
                asset, action, entry_px, exit_px, size_usd, pnl_usd, ts, reason = row
                trade_time = datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
                
                # Handle None values
                entry_px = entry_px or 0
                exit_px = exit_px or entry_px  # Use entry price if no exit
                size_usd = size_usd or 0
                pnl_usd = pnl_usd or 0
                
                trades.append({
                    "side": "long" if action == "BUY" else "short",
                    "coin": asset,
                    "entry": entry_px,
                    "exit": exit_px,
                    "qty": size_usd / entry_px if entry_px > 0 else 0,
                    "close_reason": reason or "Unknown",
                    "time": trade_time,
                    "holding": "N/A",
                    "notional": size_usd,
                    "fees": 0,
                    "pnl": pnl_usd,
                    "_meta": {"source": "sqlite"}
                })
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting SQLite trades: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []
    
    async def _get_live_equity(self) -> List[Dict[str, Any]]:
        """Get equity curve from live Hyperliquid data."""
        try:
            exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
            user = settings.HL_ACCOUNT_ADDRESS
            
            # Get portfolio for current value (rate limited)
            portfolio = await self._rate_limited_hl_call(
                "portfolio_equity",
                asyncio.to_thread(lambda: info.portfolio(user))
            )
            if not portfolio:
                return []
            
            current_value = portfolio.get("totalValue", 0)
            current_time = datetime.now()
            
            # For now, return just current point
            # In future, could implement historical equity tracking
            return [{
                "timestamp": current_time.isoformat(),
                "value": current_value,
                "_meta": {"source": "live", "point": "current"}
            }]
            
        except Exception as e:
            logger.error(f"Error getting live equity: {e}")
            return []
    
    async def _test_price_discovery(self) -> Optional[float]:
        """Test price discovery for health check."""
        try:
            exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
            price = discover_price(info, self.default_symbol)
            return price
        except Exception as e:
            logger.warning(f"Price discovery test failed: {e}")
            return None
    
    async def _test_exchange_connection(self):
        """Test exchange connection for health check."""
        try:
            exchange, info = connect(settings.HL_NETWORK, settings.HL_PRIVATE_KEY)
            # Test by getting meta data (rate limited)
            meta = await self._rate_limited_hl_call(
                "meta_health",
                asyncio.to_thread(lambda: info.meta())
            )
            return meta is not None
        except Exception as e:
            logger.warning(f"Exchange connection test failed: {e}")
            raise
    
    async def _get_last_trade_time(self) -> Optional[float]:
        """Get timestamp of last trade from SQLite."""
        try:
            conn = sqlite3.connect("data/trades.db")
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ts) FROM trades")
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                return result[0] / 1000  # Convert to seconds
            return None
        except Exception as e:
            logger.warning(f"Error getting last trade time: {e}")
            return None

# Global instance
state_service = StateService()
