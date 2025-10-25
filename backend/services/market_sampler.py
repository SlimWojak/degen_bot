"""
Rolling market sampler for data plane confidence.
Samples market data every 500ms and maintains 5-minute rolling buffers.
"""

import time
import logging
import asyncio
from typing import Dict, List, Any, Optional
from collections import deque
from dataclasses import dataclass
from backend.config import settings
from backend.services.ws_guard import ws_guard
from backend.services.rest_sampler import rest_sampler
# Import will be handled dynamically to avoid circular imports

logger = logging.getLogger(__name__)

@dataclass
class MarketSample:
    """Single market data sample."""
    ts: str
    mid: Optional[float]
    spread_bps: Optional[float]
    obi: Optional[float]
    last_msg_ms_ago: Optional[int]
    reconnects: int

class MarketSampler:
    """Rolling market sampler with 5-minute buffer and aggregates."""
    
    def __init__(self, symbols: List[str] = None, sample_interval_ms: int = 500):
        self.symbols = symbols or ["BTC", "ETH"]
        self.sample_interval_ms = sample_interval_ms
        self.buffer_size = 600  # 5 minutes at 500ms intervals
        
        # Rolling buffers for each symbol
        self.buffers: Dict[str, deque] = {
            symbol: deque(maxlen=self.buffer_size) 
            for symbol in self.symbols
        }
        
        # Connection state tracking
        self.reconnect_counts: Dict[str, int] = {symbol: 0 for symbol in self.symbols}
        self.last_reconnect_check: Dict[str, float] = {symbol: 0 for symbol in self.symbols}
        
        # Sampling state
        self.is_running = False
        self.sampler_task: Optional[asyncio.Task] = None
        self.debug_logger_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the market sampler."""
        if self.is_running:
            return
        
        self.is_running = True
        self.sampler_task = asyncio.create_task(self._sampler_loop())
        
        # Start debug logger if enabled
        if settings.DEBUG_SAMPLER:
            self.debug_logger_task = asyncio.create_task(self._debug_logger_loop())
        
        logger.info(f"Market sampler started for symbols: {self.symbols}")
    
    async def stop(self):
        """Stop the market sampler."""
        self.is_running = False
        
        if self.sampler_task:
            self.sampler_task.cancel()
            try:
                await self.sampler_task
            except asyncio.CancelledError:
                pass
        
        if self.debug_logger_task:
            self.debug_logger_task.cancel()
            try:
                await self.debug_logger_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Market sampler stopped")
    
    async def _sampler_loop(self):
        """Main sampling loop."""
        while self.is_running:
            try:
                await self._sample_all_symbols()
                await asyncio.sleep(self.sample_interval_ms / 1000.0)
            except Exception as e:
                logger.error(f"Error in sampler loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _sample_all_symbols(self):
        """Sample all symbols and update buffers."""
        for symbol in self.symbols:
            try:
                sample = await self._sample_symbol(symbol)
                if sample:
                    self.buffers[symbol].append(sample)
            except Exception as e:
                logger.warning(f"Failed to sample {symbol}: {e}")
    
    async def _sample_symbol(self, symbol: str) -> Optional[MarketSample]:
        """Sample a single symbol."""
        try:
            # Get market data from cache (non-blocking)
            from backend.services.market_cache import get_cached
            cached_tick = get_cached(symbol)
            if not cached_tick:
                return None
            
            # Extract data from cache
            mid = cached_tick.mid
            spread_bps = cached_tick.spread_bps
            obi = cached_tick.obi
            
            # Calculate last_msg_ms_ago using monotonic time
            last_msg_ms_ago = None
            if cached_tick.last_tick_ts > 0:
                last_msg_ms_ago = int((time.time() - cached_tick.last_tick_ts) * 1000)
            
            # Get reconnects from market feed (if available)
            current_reconnects = 0
            try:
                # Try to get from app state if available
                import sys
                if 'app' in sys.modules:
                    app = sys.modules['app']
                    if hasattr(app, 'state') and hasattr(app.state, 'market_feed') and app.state.market_feed:
                        current_reconnects = app.state.market_feed.get_reconnect_count()
            except Exception:
                pass  # Use default 0 if not available
            
            return MarketSample(
                ts=time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
                mid=mid,
                spread_bps=spread_bps,
                obi=obi,
                last_msg_ms_ago=last_msg_ms_ago,
                reconnects=current_reconnects
            )
            
        except Exception as e:
            logger.warning(f"Error sampling {symbol}: {e}")
            return None
    
    async def _debug_logger_loop(self):
        """Debug logging loop - runs every 60 seconds."""
        while self.is_running:
            try:
                await asyncio.sleep(60.0)  # 60 seconds
                self._log_sampler_stats()
            except Exception as e:
                logger.error(f"Error in debug logger: {e}")
    
    def _log_sampler_stats(self):
        """Log sampler statistics for debug visibility."""
        try:
            stats = self.get_health_metrics()
            
            # Log per-symbol stats
            for symbol in self.symbols:
                mids_pct = stats["mids_nonnull_pct"].get(symbol, 0.0)
                avg_delay = stats["avg_last_msg_ms_ago"].get(symbol, 0)
                reconnects = stats["reconnects_5m"].get(symbol, 0)
                
                logger.info(
                    f"[sampler] {symbol} mid ok={mids_pct:.1%} "
                    f"avg_delay={avg_delay}ms reconnects={reconnects}"
                )
            
            # Log overall status
            status = stats["status"]
            logger.info(f"[sampler] status={status.upper()}")
            
        except Exception as e:
            logger.error(f"Error logging sampler stats: {e}")
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get aggregated health metrics with degraded mode support."""
        try:
            # Check if WebSocket is blocked
            ws_blocked = ws_guard.is_blocked()
            block_info = ws_guard.get_block_info()
            
            metrics = {
                "window_s": 300,  # 5 minutes
                "symbols": self.symbols,
                "mids_nonnull_pct": {},
                "avg_last_msg_ms_ago": {},
                "reconnects_5m": {},
                "status": "degraded" if ws_blocked else "healthy",
                "notes": []
            }
            
            # Add degraded mode information
            if ws_blocked:
                metrics["notes"].append("ws_blocked_policy_violation")
                metrics["ws_blocked"] = True
                metrics["blocked_until"] = block_info.get("blocked_until")
                metrics["rest_meta_ok"] = rest_sampler.get_health_info().get("rest_meta_ok", False)
            else:
                metrics["ws_blocked"] = False
            
            for symbol in self.symbols:
                buffer = self.buffers[symbol]
                
                if not buffer:
                    metrics["mids_nonnull_pct"][symbol] = 0.0
                    metrics["avg_last_msg_ms_ago"][symbol] = 0
                    metrics["reconnects_5m"][symbol] = 0
                    continue
                
                # Calculate mids_nonnull_pct
                total_samples = len(buffer)
                nonnull_mids = sum(1 for sample in buffer if sample.mid is not None)
                mids_pct = nonnull_mids / total_samples if total_samples > 0 else 0.0
                metrics["mids_nonnull_pct"][symbol] = mids_pct
                
                # Calculate avg_last_msg_ms_ago
                valid_delays = [s.last_msg_ms_ago for s in buffer if s.last_msg_ms_ago is not None]
                avg_delay = sum(valid_delays) / len(valid_delays) if valid_delays else 0
                metrics["avg_last_msg_ms_ago"][symbol] = int(avg_delay)
                
                # Calculate reconnects_5m
                if buffer:
                    current_reconnects = buffer[-1].reconnects
                    initial_reconnects = buffer[0].reconnects if buffer else 0
                    reconnects_5m = max(0, current_reconnects - initial_reconnects)
                    metrics["reconnects_5m"][symbol] = reconnects_5m
                else:
                    metrics["reconnects_5m"][symbol] = 0
            
            # Determine overall status
            all_mids_ok = all(
                metrics["mids_nonnull_pct"][symbol] >= 0.95 
                for symbol in self.symbols
            )
            all_delays_ok = all(
                metrics["avg_last_msg_ms_ago"][symbol] < 1500 
                for symbol in self.symbols
            )
            all_reconnects_ok = all(
                metrics["reconnects_5m"][symbol] <= 2 
                for symbol in self.symbols
            )
            
            if not all_mids_ok:
                metrics["notes"].append("mid gaps detected")
            if not all_delays_ok:
                metrics["notes"].append("high latency detected")
            if not all_reconnects_ok:
                metrics["notes"].append("excessive reconnects detected")
            
            if not (all_mids_ok and all_delays_ok and all_reconnects_ok):
                metrics["status"] = "degraded"
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error calculating health metrics: {e}")
            return {
                "window_s": 300,
                "symbols": self.symbols,
                "mids_nonnull_pct": {},
                "avg_last_msg_ms_ago": {},
                "reconnects_5m": {},
                "status": "error",
                "notes": [f"Error: {str(e)}"]
            }
    
    def get_latest_samples(self, symbol: str, count: int = 10) -> List[MarketSample]:
        """Get latest samples for a symbol."""
        buffer = self.buffers.get(symbol, deque())
        return list(buffer)[-count:]

# Global sampler instance
_sampler: Optional[MarketSampler] = None

async def start_market_sampler():
    """Start the global market sampler."""
    global _sampler
    if _sampler is None:
        _sampler = MarketSampler()
    await _sampler.start()

async def stop_market_sampler():
    """Stop the global market sampler."""
    global _sampler
    if _sampler is not None:
        await _sampler.stop()

def get_sampler() -> Optional[MarketSampler]:
    """Get the global sampler instance."""
    return _sampler

def get_data_health_info() -> Dict[str, Any]:
    """Get data health information from the global sampler."""
    global _sampler
    if _sampler is None:
        return {
            "status": "degraded",
            "mids_nonnull_pct": {},
            "avg_last_msg_ms_ago": {},
            "reconnects_5m": {}
        }
    return _sampler.get_health_metrics()
