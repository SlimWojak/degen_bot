"""
LEGACY MARKET WEBSOCKET SERVICE - REMOVED

This module has been replaced by backend.services.hyperliquid_ws.HyperliquidWSClient.
All legacy MarketDataService functionality has been moved to the unified Hyperliquid feed.

This import trap will crash immediately and print the exact file/line that imported it.
"""

import logging
import traceback

log = logging.getLogger("legacy_import_trap")
log.critical("LEGACY IMPORT TRIGGERED: backend.services.market_ws")
log.critical("Import stack:\n%s", "".join(traceback.format_stack(limit=30)))

raise ImportError(
    "Legacy MarketDataService is removed. Use backend.services.hyperliquid_ws.HyperliquidWSClient instead. "
    "The unified Hyperliquid feed provides better performance, proper heartbeat, and rate limiting."
)

logger = logging.getLogger(__name__)

# Module-level lock to ensure only one connection task at a time
_connection_lock = asyncio.Lock()
_global_connection_count = 0
_duplicate_connection_attempts = 0

# Canonical symbol mapping
CANONICAL_SYMBOLS = {
    'BTC': 'BTC',
    'ETH': 'ETH', 
    'SOL': 'SOL',
    'btc': 'BTC',
    'eth': 'ETH',
    'sol': 'SOL',
    'Bitcoin': 'BTC',
    'Ethereum': 'ETH',
    'Solana': 'SOL'
}

def normalize_symbol(symbol: str) -> Optional[str]:
    """Normalize symbol to canonical form."""
    return CANONICAL_SYMBOLS.get(symbol, None)

class MarketDataService:
    """Market data service with WebSocket connection and microstructure computation."""
    
    def __init__(self, symbols: List[str], ws_url: str):
        self.symbols = symbols
        self.ws_url = ws_url
        self.ws = None
        self.running = False
        
        # Reconnection state
        self.backoff_ms = settings.HL_WS_MIN_RECONNECT_MS
        self.min_backoff_ms = settings.HL_WS_MIN_RECONNECT_MS
        self.max_backoff_ms = settings.HL_WS_BACKOFF_MAX_MS
        self.jitter_ms = settings.HL_WS_JITTER_MS
        self.connection_task = None
        
        # Per-symbol state
        self.symbol_state: Dict[str, dict] = {}
        
        # Initialize per-symbol buffers and state
        for symbol in symbols:
            # Ring buffer capacity based on buffer_secs and tick_ms
            capacity = (settings.MARKET_WS_BUFFER_SECS * 1000) // settings.MARKET_WS_TICK_MS
            
            self.symbol_state[symbol] = {
                'micro_buffer': RingBuffer[Microstructure](capacity),
                'mids_buffer': deque(maxlen=(settings.MARKET_MID_HISTORY_MIN * 60) // settings.MARKET_MID_BUCKET_S),
                'latest_book': None,
                'latest_trades': deque(maxlen=200),
                'last_micro_ts': 0,
                'last_mid_ts': 0
            }
        
        # Health tracking
        self.health = MarketHealth(
            ws="down",
            lag_ms=0,
            symbols_connected=[],
            last_update_ts=0,
            error_count=0
        )
        
        # Background tasks
        self.tasks: List[asyncio.Task] = []
    
    async def start(self) -> None:
        """Start the market data service."""
        global _global_connection_count, _duplicate_connection_attempts
        
        if not settings.MARKET_WS_ENABLED:
            logger.info("Market WS disabled, skipping start")
            return
        
        async with _connection_lock:
            if self.connection_task and not self.connection_task.done():
                _duplicate_connection_attempts += 1
                logger.warning(f"Connection already in progress (duplicate attempt #{_duplicate_connection_attempts})")
                return
            
            if _global_connection_count > 0:
                _duplicate_connection_attempts += 1
                logger.warning(f"Another WS connection already exists (duplicate attempt #{_duplicate_connection_attempts})")
                return
            
            self.running = True
            _global_connection_count += 1
            logger.info(f"Starting market WS service for symbols: {self.symbols} (connection #{_global_connection_count})")
            
            # Start background tasks
            self.tasks.append(asyncio.create_task(self._ws_loop()))
            self.tasks.append(asyncio.create_task(self._micro_loop()))
            
            logger.info("Market WS service started")
    
    async def stop(self) -> None:
        """Stop the market data service."""
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close WebSocket
        if self.ws:
            await self.ws.close()
        
        logger.info("Market WS service stopped")
    
    async def _ws_loop(self) -> None:
        """WebSocket connection loop with exponential backoff and connection hygiene."""
        while self.running:
            try:
                async with _connection_lock:
                    if self.connection_task and not self.connection_task.done():
                        logger.info("Connection already in progress, waiting...")
                        await self.connection_task
                        continue
                    
                    # Create new connection task
                    self.connection_task = asyncio.create_task(self._connect_and_process())
                    await self.connection_task
                    
            except Exception as e:
                await self._handle_connection_error(e)
    
    async def _connect_and_process(self) -> None:
        """Connect to WebSocket and process messages."""
        try:
            logger.info(f"Connecting to market WS: {self.ws_url}")
            async with websockets.connect(self.ws_url) as ws:
                self.ws = ws
                self.health.ws = "connected"
                self.backoff_ms = self.min_backoff_ms  # Reset backoff on successful connection
                
                # Subscribe to market data
                await self._subscribe_to_symbols(ws)
                
                # Process messages
                async for message in ws:
                    if not self.running:
                        break
                    await self._process_message(message)
                    
        except Exception as e:
            raise e  # Re-raise to be handled by _handle_connection_error
    
    async def _handle_connection_error(self, error: Exception) -> None:
        """Handle connection errors with exponential backoff and jitter."""
        self.health.ws = "reconnecting"
        self.health.error_count += 1
        
        # Calculate backoff with jitter
        jitter = random.randint(0, self.jitter_ms)
        sleep_ms = max(self.min_backoff_ms, min(self.backoff_ms * 2, self.max_backoff_ms)) + jitter
        
        # Log structured JSON for monitoring
        logger.error(json.dumps({
            "evt": "ws_reconnect",
            "sleep_ms": sleep_ms,
            "reason": str(error),
            "backoff_ms": self.backoff_ms,
            "error_count": self.health.error_count
        }))
        
        # Update backoff for next attempt
        self.backoff_ms = min(self.backoff_ms * 2, self.max_backoff_ms)
        
        # Sleep before retry
        await asyncio.sleep(sleep_ms / 1000.0)
    
    async def _subscribe_to_symbols(self, ws) -> None:
        """Subscribe to market data for all symbols."""
        for symbol in self.symbols:
            # Subscribe to order book updates
            subscribe_msg = {
                "method": "subscribe",
                "subscription": {
                    "type": "l2Book",
                    "coin": symbol
                }
            }
            await ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to L2 book for {symbol}")
    
    async def _process_message(self, message: str) -> None:
        """Process incoming WebSocket message."""
        try:
            data = json.loads(message)
            
            # Handle different message types
            if data.get("channel") == "l2Book":
                await self._handle_l2_book(data)
            elif data.get("channel") == "trades":
                await self._handle_trades(data)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_l2_book(self, data: dict) -> None:
        """Handle L2 book update."""
        symbol = data.get("data", {}).get("coin")
        if not symbol or symbol not in self.symbols:
            return
        
        # Update latest book
        book_data = data.get("data", {})
        self.symbol_state[symbol]['latest_book'] = {
            'ts': int(time.time() * 1000),
            'bids': book_data.get('levels', [])[:settings.MARKET_WS_BOOK_DEPTH],
            'asks': book_data.get('levels', [])[:settings.MARKET_WS_BOOK_DEPTH]
        }
        
        self.health.last_update_ts = int(time.time() * 1000)
        if symbol not in self.health.symbols_connected:
            self.health.symbols_connected.append(symbol)
    
    async def _handle_trades(self, data: dict) -> None:
        """Handle trades update."""
        symbol = data.get("data", {}).get("coin")
        if not symbol or symbol not in self.symbols:
            return
        
        # Store recent trades
        trades = data.get("data", {}).get("trades", [])
        for trade in trades:
            self.symbol_state[symbol]['latest_trades'].append({
                'ts': int(time.time() * 1000),
                'px': float(trade.get('px', 0)),
                'sz': float(trade.get('sz', 0)),
                'side': trade.get('side', 'buy')
            })
    
    async def _micro_loop(self) -> None:
        """Microstructure computation loop."""
        while self.running:
            try:
                current_ts = int(time.time() * 1000)
                
                for symbol in self.symbols:
                    state = self.symbol_state[symbol]
                    
                    # Check if we have fresh book data
                    if not state['latest_book']:
                        continue
                    
                    # Compute microstructure features
                    micro = await self._compute_microstructure(symbol, current_ts)
                    if micro:
                        state['micro_buffer'].append(micro)
                        state['last_micro_ts'] = current_ts
                
                # Sleep for tick interval
                await asyncio.sleep(settings.MARKET_WS_TICK_MS / 1000.0)
                
            except Exception as e:
                logger.error(f"Error in micro loop: {e}")
                await asyncio.sleep(1)
    
    async def _compute_microstructure(self, symbol: str, ts: int) -> Optional[Microstructure]:
        """Compute microstructure features for a symbol."""
        state = self.symbol_state[symbol]
        book = state['latest_book']
        
        if not book or not book.get('bids') or not book.get('asks'):
            return None
        
        try:
            # Get best bid/ask
            best_bid = book['bids'][0] if book['bids'] else None
            best_ask = book['asks'][0] if book['asks'] else None
            
            if not best_bid or not best_ask:
                return None
            
            bid_px, bid_sz = float(best_bid['px']), float(best_bid['sz'])
            ask_px, ask_sz = float(best_ask['px']), float(best_ask['sz'])
            
            # Basic features
            mid = (bid_px + ask_px) / 2
            spread_bps = ((ask_px - bid_px) / mid) * 10000
            
            # Depth calculations
            depth_bid_usd = sum(float(level['px']) * float(level['sz']) for level in book['bids'])
            depth_ask_usd = sum(float(level['px']) * float(level['sz']) for level in book['asks'])
            
            # Order book imbalance
            total_bid_sz = sum(float(level['sz']) for level in book['bids'])
            total_ask_sz = sum(float(level['sz']) for level in book['asks'])
            obi = (total_bid_sz - total_ask_sz) / (total_bid_sz + total_ask_sz + 1e-9)
            
            # Order flow imbalance (simplified)
            ofi = 0.0  # TODO: Implement proper OFI calculation
            
            # Microprice
            microprice = (ask_px * bid_sz + bid_px * ask_sz) / (bid_sz + ask_sz + 1e-9)
            
            # Price impact (simplified)
            impact_usd = {
                "15": 0.0,  # TODO: Implement proper impact calculation
                "25": 0.0,
                "50": 0.0
            }
            
            # Returns (if we have enough history)
            rtn_5s = self._compute_return(symbol, 5)
            rtn_30s = self._compute_return(symbol, 30)
            
            # Update cache with tick data
            update_tick(symbol, mid=mid, spread_bps=spread_bps, obi=obi)
            
            return Microstructure(
                ts=ts,
                mid=mid,
                spread_bps=spread_bps,
                depth_bid_usd=depth_bid_usd,
                depth_ask_usd=depth_ask_usd,
                obi=obi,
                ofi=ofi,
                microprice=microprice,
                impact_usd=impact_usd,
                rtn_5s=rtn_5s,
                rtn_30s=rtn_30s
            )
            
        except Exception as e:
            logger.error(f"Error computing microstructure for {symbol}: {e}")
            return None
    
    def _compute_return(self, symbol: str, window_seconds: int) -> Optional[float]:
        """Compute return over specified window."""
        state = self.symbol_state[symbol]
        mids = list(state['mids_buffer'])
        
        if len(mids) < 2:
            return None
        
        # Get mid from window_seconds ago
        current_ts = int(time.time() * 1000)
        target_ts = current_ts - (window_seconds * 1000)
        
        # Find closest mid to target time
        closest_mid = None
        for ts, mid in mids:
            if ts <= target_ts:
                closest_mid = mid
            else:
                break
        
        if closest_mid is None:
            return None
        
        current_mid = mids[-1][1] if mids else None
        if current_mid is None:
            return None
        
        return (current_mid - closest_mid) / closest_mid
    
    def get_snapshot(self, symbol: str) -> Optional[Snapshot]:
        """Get market snapshot for a symbol."""
        if symbol not in self.symbols:
            return None
        
        state = self.symbol_state[symbol]
        book = state['latest_book']
        
        if not book:
            return None
        
        # Get latest microstructure
        micro = state['micro_buffer'].get_latest() if state['micro_buffer'] else None
        if not micro:
            return None
        
        # Build book sides
        bids = BookSide(levels=[BookLevel(px=float(level['px']), sz=float(level['sz'])) 
                        for level in book['bids']])
        asks = BookSide(levels=[BookLevel(px=float(level['px']), sz=float(level['sz'])) 
                        for level in book['asks']])
        
        return Snapshot(
            symbol=symbol,
            book_ts=book['ts'],
            bids=bids,
            asks=asks,
            micro=micro
        )
    
    def get_micro(self, symbol: str) -> Optional[Microstructure]:
        """Get latest microstructure for a symbol."""
        if symbol not in self.symbols:
            return None
        
        state = self.symbol_state[symbol]
        return state['micro_buffer'].get_latest() if state['micro_buffer'] else None
    
    def get_health(self) -> MarketHealth:
        """Get service health status."""
        current_ts = int(time.time() * 1000)
        lag_ms = current_ts - self.health.last_update_ts if self.health.last_update_ts else 0
        
        return MarketHealth(
            ws=self.health.ws,
            lag_ms=lag_ms,
            symbols_connected=self.health.symbols_connected.copy(),
            last_update_ts=self.health.last_update_ts,
            error_count=self.health.error_count
        )
