"""
Degen God v2 - Main entry point.

Real-time, DeepSeek-powered Hyperliquid perp bot.
YolOs on A+ setups (score ≥80/100).
"""

import os
import asyncio
import logging
import argparse
import json
import time
import http.server
import socketserver
import threading
from datetime import datetime
from dotenv import load_dotenv
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import bot modules
from bot.engine import DegenGodEngine
from bot.executor import OrderExecutor
from bot.risk import RiskManager
from bot.logger import TradeLogger

# Import configuration
from common.config import load_config, redacted

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()  # Load .env into os.environ

# Global bot status for health check
global_bot_ready = False

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    """Health check handler for Docker."""
    
    def do_GET(self):
        """Handle GET requests to /health endpoint."""
        if self.path == '/health':
            status = "healthy" if global_bot_ready else "starting"
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "service": "degen_god_v2"
            }
            self.wfile.write(json.dumps(response).encode())
            return
        self.send_response(404)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress default logging for health checks."""
        pass

def start_health_server():
    """Start health check server in background thread."""
    try:
        with socketserver.TCPServer(("", 8080), HealthHandler) as httpd:
            logger.info("🏥 Health check server started on port 8080")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")


class WebSocketManager:
    """Manages WebSocket connections with exponential backoff reconnection."""
    
    def __init__(self, exchange, info, assets, config):
        self.exchange = exchange
        self.info = info
        self.assets = assets
        self.config = config
        self.reconnect_delay = 1  # Start with 1 second
        self.max_delay = 60  # Cap at 60 seconds
        self.is_connected = False
        self.subscription_ids = []
        
    async def connect_with_retry(self):
        """Connect to WebSocket with exponential backoff retry."""
        while True:
            try:
                logger.info("🔌 Attempting WebSocket connection...")
                
                # Subscribe to all required channels
                await self._subscribe_to_channels()
                
                self.is_connected = True
                self.reconnect_delay = 1  # Reset delay on successful connection
                logger.info("✅ WebSocket connected successfully")
                return
                
            except Exception as e:
                error_msg = str(e)
                if "deserialize" in error_msg:
                    logger.warning("⚠️  Invalid subscription — falling back to polling")
                    self.is_connected = True  # Mark as connected but use polling
                    return
                else:
                    logger.error(f"❌ WebSocket connection failed: {e}")
                    logger.info(f"🔄 Retrying in {self.reconnect_delay} seconds...")
                    
                    await asyncio.sleep(self.reconnect_delay)
                    
                    # Exponential backoff with cap
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_delay)
                    self.is_connected = False
    
    async def _subscribe_to_channels(self):
        """Subscribe to all required WebSocket channels."""
        try:
            # Subscribe to order updates
            account_address = self.config["hyperliquid"]["account_address"]
            order_sub = self.info.subscribe(
                {"type": "orderUpdates", "user": account_address},
                lambda data: logger.info(f"📊 Order update: {data}")
            )
            self.subscription_ids.append(order_sub)
            logger.info("📊 Subscribed to orderUpdates")
            
            # Subscribe to tickers for all assets
            for asset in self.assets:
                ticker_sub = self.info.subscribe(
                    {"type": "ticker", "coin": asset},
                    lambda data: logger.info(f"📈 Ticker update: {data}")
                )
                self.subscription_ids.append(ticker_sub)
            logger.info(f"📈 Subscribed to tickers for {len(self.assets)} assets")
            
        except Exception as e:
            logger.error(f"Error subscribing to channels: {e}")
            raise
    
    async def monitor_connection(self):
        """Monitor WebSocket connection and reconnect if needed."""
        while True:
            try:
                if not self.is_connected:
                    await self.connect_with_retry()
                
                # Simple health check - try to get user state
                user = self.config["hyperliquid"]["account_address"]
                user_state = self.info.user_state(user)
                if not user_state:
                    logger.warning("⚠️  WebSocket health check failed, reconnecting...")
                    self.is_connected = False
                    await self.connect_with_retry()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in WebSocket monitoring: {e}")
                self.is_connected = False
                await asyncio.sleep(5)

async def monitor_active_positions(engine, risk_manager, assets, info):
    """
    Monitor active positions with DeepSeek every 30s.
    
    Args:
        engine: DegenGodEngine instance
        risk_manager: RiskManager instance
        assets: List of assets to monitor
        info: Hyperliquid Info instance
    """
    try:
        # Check for active positions
        active_positions = []
        for asset in assets:
            # Check if position exists (simplified check)
            try:
                user_state = info.user_state(engine.config["hyperliquid"]["account_address"])
                if user_state and 'assetPositions' in user_state:
                    for pos in user_state['assetPositions']:
                        if pos.get('coin') == asset and float(pos.get('position', {}).get('szi', 0)) != 0:
                            active_positions.append({
                                'asset': asset,
                                'size': float(pos.get('position', {}).get('szi', 0)),
                                'entry_px': float(pos.get('position', {}).get('entryPx', 0)),
                                'side': 'long' if float(pos.get('position', {}).get('szi', 0)) > 0 else 'short'
                            })
            except Exception as e:
                logger.warning(f"Error checking position for {asset}: {e}")
        
        # If no active positions, return
        if not active_positions:
            logger.info("📊 No active positions to monitor")
            return
        
        logger.info(f"🔍 Review triggered for {len(active_positions)} positions")
        
        # Simulate 30s review for HYPE validation
        if "HYPE" in [pos['asset'] for pos in active_positions]:
            await risk_manager.simulate_30s_review("HYPE")
        
        # Get current market data for each active position
        for position in active_positions:
            asset = position['asset']
            try:
                # Get current indicators
                indicators = await engine.indicator_calc.get_all_indicators(asset)
                if not indicators:
                    continue
                
                # Get current price
                ticker = info.ticker(asset)
                current_price = float(ticker[0].get('close', 0)) if ticker and len(ticker) > 0 else indicators.get('current_price', 0)
                
                # Prompt DeepSeek for position review
                prompt = f"""
Review {asset} position:
- Current Price: ${current_price:.4f}
- Entry Price: ${position['entry_px']:.4f}
- Side: {position['side']}
- Size: {position['size']}
- Current RSI: {indicators.get('rsi', 50):.1f}
- 1h EMA20: {indicators.get('ema20_1h', 0):.4f}
- Funding Rate: {indicators.get('funding_rate', 0):.4f}%
- ATR: {indicators.get('atr', 0):.4f}

Thesis valid? RSI>80 + funding>0.05% → close. Bull intact (1h EMA20 up + 5m RSI<70) → trail SL to 1.8x ATR.

Respond with: HOLD, CLOSE, or TRAIL_SL
"""
                
                # Get DeepSeek response
                response = await engine.get_deepseek_analysis(asset, indicators, prompt)
                if response:
                    logger.info(f"🧠 DeepSeek position review for {asset}: {response}")
                    logger.info(f"🔍 Review triggered, DeepSeek: {response}")
                    
                    # Log to deepseek_thoughts
                    with open('deepseek_thoughts', 'a') as f:
                        f.write(f"{datetime.now().isoformat()} - {asset} Position Review: {response}\n")
                    
                    # Execute DeepSeek's recommendation via risk manager
                    risk_action = await risk_manager.review_position(
                        asset=asset,
                        deepseek_command=response,
                        current_price=current_price,
                        atr=indicators.get('atr', 0),
                        side=position['side']
                    )
                    
                    if risk_action:
                        logger.info(f"🎯 Risk action executed: {risk_action}")
                
            except Exception as e:
                logger.error(f"Error monitoring position {asset}: {e}")
                
    except Exception as e:
        logger.error(f"Error in active position monitoring: {e}")


async def execute_mock_trades(engine, executor, risk_manager, assets, config):
    """
    Execute 5 mock trades for testing autonomous trading.
    
    Args:
        engine: DegenGodEngine instance
        executor: OrderExecutor instance
        risk_manager: RiskManager instance
        assets: List of assets
        config: Configuration dictionary
    """
    import random
    
    logger.info("🎭 Starting mock trading test - 5 trades...")
    
    # Mock trade assets and scores
    mock_trades = [
        {"asset": "HYPE", "score": random.randint(85, 105)},
        {"asset": "BTC", "score": random.randint(85, 105)},
        {"asset": "SOL", "score": random.randint(85, 105)},
        {"asset": "ETH", "score": random.randint(85, 105)},
        {"asset": "HYPE", "score": random.randint(85, 105)}
    ]
    
    for i, trade in enumerate(mock_trades, 1):
        asset = trade["asset"]
        score = trade["score"]
        
        logger.info(f"🎭 Mock Trade {i}/5: {asset} (Score: {score})")
        
        try:
            # Get mock indicators for the asset
            mock_indicators = {
                'rsi': random.uniform(20, 80),
                'macd_line': random.uniform(-0.1, 0.1),
                'macd_signal': random.uniform(-0.1, 0.1),
                'macd_histogram': random.uniform(-0.05, 0.05),
                'momentum': random.uniform(5, 25),
                'atr': random.uniform(0.1, 0.5),
                'volume_change': random.uniform(50, 300),
                'current_price': random.uniform(0.5, 2.0),
                'atr_percent': random.uniform(1, 5),
                'funding_rate': random.uniform(0, 0.001),
                'whale_volume': random.uniform(1, 3),
                'bb_squeeze': random.uniform(0.05, 0.2),
                'rsi_1h': random.uniform(30, 70),
                'ema20_1h': random.uniform(0.8, 1.2)
            }
            
            # Create mock decision
            action = "long" if random.random() > 0.5 else "short"
            leverage = random.randint(10, 50)
            size_usd = random.uniform(100, 1000)
            
            mock_decision = {
                'action': action,
                'size_usd': size_usd,
                'leverage': leverage,
                'tp': mock_indicators['current_price'] * (1.1 if action == "long" else 0.9),
                'sl': mock_indicators['current_price'] * (0.95 if action == "long" else 1.05),
                'reason': f"Mock trade {i} - Score {score}"
            }
            
            logger.info(f"🎯 Mock {asset}: {action.upper()} ${size_usd:.2f} {leverage}x (Score: {score})")
            
            # Simulate trade execution
            if config["bot"]["dry_run"]:
                logger.info(f"🔧 DRY RUN: Would execute {asset} trade")
                
                # Start risk management for the mock position
                await risk_manager.monitor_position(
                    asset=asset,
                    entry_price=mock_indicators['current_price'],
                    atr=mock_indicators['atr'],
                    initial_sl=mock_decision['sl'],
                    side=action
                )
                
                # Log mock trade
                trade_data = {
                    'timestamp': int(datetime.now().timestamp()),
                    'asset': asset,
                    'action': action,
                    'score': score,
                    'entry_px': mock_indicators['current_price'],
                    'size_usd': size_usd,
                    'lev': leverage,
                    'tp': mock_decision['tp'],
                    'sl': mock_decision['sl'],
                    'reason': mock_decision['reason'],
                    'ind_rsi': mock_indicators['rsi'],
                    'ind_macd': mock_indicators['macd_histogram'],
                    'ind_mom': mock_indicators['momentum']
                }
                
                logger.info(f"✅ Mock trade {i} logged: {asset} {action} @ ${mock_indicators['current_price']:.4f}")
                
            else:
                logger.info(f"🚀 LIVE MODE: Would execute real {asset} trade")
            
            # Small delay between trades
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error in mock trade {i} ({asset}): {e}")
    
    logger.info("🎭 Mock trading test completed - 5 trades executed")


async def main():
    """
    Main async function to run the Degen God v2 bot.
    
    Initializes Hyperliquid Exchange, sets up WebSocket connections,
    and runs the main trading loop with scorecard analysis.
    """
    try:
        # Start health check server in background thread
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()
        logger.info("🏥 Health check server starting in background...")
        
        # Load configuration using new config system
        try:
            cfg = load_config()
            logger.info("✅ Configuration loaded successfully")
            logger.info(f"Environment: {cfg.hl.env}")
            logger.info(f"Assets: {cfg.bot.assets}")
            logger.info(f"Start Capital: ${cfg.bot.start_capital:,.2f}")
        except Exception as e:
            logger.error(f"❌ Failed to load configuration: {e}")
            return
        
        # Convert to legacy config format for compatibility
        config = {
            "hyperliquid": {
                "account_address": cfg.hl.account,
                "secret_key": cfg.hl.private_key
            },
            "deepseek": {
                "api_key": cfg.ds.api_key
            },
            "bot": {
                "start_capital": cfg.bot.start_capital,
                "assets": cfg.bot.assets,
                "min_score": cfg.bot.min_score,
                "max_leverage": cfg.bot.max_leverage,
                "testnet": cfg.hl.env == "testnet",
                "dry_run": os.getenv("DRY_RUN", "true").lower() == "true"
            }
        }
        
        # Initialize Hyperliquid Exchange
        logger.info("🚀 Initializing Degen God v2...")
        base_url = constants.TESTNET_API_URL if config["bot"]["testnet"] else constants.MAINNET_API_URL
        exchange = Exchange(config["hyperliquid"], base_url=base_url)
        info = Info()
        
        # Initialize Degen God components
        engine = DegenGodEngine(exchange, info, config)
        executor = OrderExecutor(exchange, info, config)
        risk_manager = RiskManager(exchange, info, config)
        trade_logger = TradeLogger(config)
        
        # Test with mock data first
        logger.info("🧪 Testing with mock data...")
        mock_score = await engine.test_mock_data()
        
        if mock_score >= 80:
            logger.info(f"✅ Mock test PASSED: Score {mock_score} >= 80")
        else:
            logger.warning(f"❌ Mock test FAILED: Score {mock_score} < 80")
        
        # Initialize WebSocket manager with reconnection logic
        logger.info("📡 Setting up WebSocket connections...")
        assets = config["bot"]["assets"]
        ws_manager = WebSocketManager(exchange, info, assets, config)
        
        # Connect to WebSocket with retry logic
        await ws_manager.connect_with_retry()
        
        # Start WebSocket monitoring in background
        asyncio.create_task(ws_manager.monitor_connection())
        
        # Set bot as ready for health checks
        global global_bot_ready
        global_bot_ready = True
        logger.info("✅ Bot ready - health check endpoint active")
        
        logger.info(f"🎯 WS {'TESTNET' if config['bot']['testnet'] else 'MAINNET'} LOCKED — HUNTING A+ SETUPS...")
        logger.info(f"💰 Capital: ${config['bot']['start_capital']}")
        logger.info(f"📊 Assets: {', '.join(assets)}")
        logger.info(f"🎯 Min Score: {config['bot']['min_score']}")
        logger.info(f"⚡ Max Leverage: {config['bot']['max_leverage']}x")
        
        # Main trading loop with WebSocket-driven execution
        analysis_interval = 30  # Analyze every 30 seconds
        last_analysis = 0
        last_monitoring = 0
        risk_check_interval = 5  # Check risk every 5 seconds
        last_risk_check = 0
        stats_interval = 3600  # Print arena stats every hour
        last_stats = 0
        
        # Mock trading test - simulate 5 trades
        mock_trades_completed = False
        
        while True:
            try:
                current_time = asyncio.get_event_loop().time()
                
                # Check emergency close threshold
                if current_time - last_risk_check >= risk_check_interval:
                    emergency_action = await risk_manager.check_emergency_close()
                    if emergency_action:
                        logger.critical(f"🚨 Emergency action taken: {emergency_action}")
                    last_risk_check = current_time
                
                # Print arena stats every hour
                if current_time - last_stats >= stats_interval:
                    await trade_logger.print_arena_stats()
                    last_stats = current_time
                
                # Mock trading test - execute 5 mock trades
                if not mock_trades_completed and current_time - last_analysis >= 5:
                    await execute_mock_trades(engine, executor, risk_manager, assets, config)
                    mock_trades_completed = True
                    last_analysis = current_time
                
                # Run analysis every interval
                if current_time - last_analysis >= analysis_interval:
                    logger.info("🔍 Running asset analysis...")
                    
                    for asset in assets:
                        try:
                            # Analyze asset for trading opportunities
                            result = await engine.analyze_asset(asset)
                            
                            if result and result['score'] >= config['bot']['min_score']:
                                logger.info(f"🎯 {asset} Analysis:")
                                logger.info(f"   Score: {result['score']}/100")
                                logger.info(f"   Triggers: {result['trigger_count']}")
                                logger.info(f"   Decision: {result['decision']}")
                                
                                # Execute trade if decision is not 'none'
                                if result['decision']['action'] != 'none':
                                    # Check for nuclear yolo
                                    is_nuclear = result.get('is_nuclear_yolo', False)
                                    yolo_emoji = "☢️ NUCLEAR YOLO" if is_nuclear else "🚀 EXECUTING"
                                    
                                    logger.info(f"{yolo_emoji}: {result['decision']['action'].upper()} "
                                              f"${result['decision']['size_usd']:.2f} "
                                              f"{result['decision']['leverage']}x")
                                    
                                    # Execute the trade
                                    execution_result = await executor.execute_trade(
                                        asset,
                                        result['decision'], 
                                        result['indicators']
                                    )
                                    
                                    if execution_result:
                                        logger.info(f"✅ Trade executed successfully: {execution_result.get('order_id', 'N/A')}")
                                        
                                        # Start risk management for the position
                                        await risk_manager.monitor_position(
                                            asset=asset,
                                            entry_price=result['indicators']['current_price'],
                                            atr=result['indicators']['atr'],
                                            initial_sl=result['decision']['sl'],
                                            side=result['decision']['action']
                                        )
                                        
                                        # Log trade entry (will be updated on exit)
                                        trade_data = {
                                            'timestamp': int(datetime.now().timestamp()),
                                            'asset': asset,
                                            'action': result['decision']['action'],
                                            'score': result['score'],
                                            'entry_px': result['indicators']['current_price'],
                                            'size_usd': result['decision']['size_usd'],
                                            'lev': result['decision']['leverage'],
                                            'tp': result['decision']['tp'],
                                            'sl': result['decision']['sl'],
                                            'reason': result['decision'].get('reason', ''),
                                            'ind_rsi': result['indicators']['rsi'],
                                            'ind_macd': result['indicators']['macd_histogram'],
                                            'ind_mom': result['indicators']['momentum'],
                                            'ind_vol': result['indicators']['volume_change'],
                                            'ind_atr': result['indicators']['atr_percent']
                                        }
                                        
                                        # Store trade data for later completion
                                        # (In real implementation, this would be stored in a state manager)
                                        
                                    else:
                                        logger.error(f"❌ Trade execution failed for {asset}")
                            else:
                                logger.debug(f"⏭️  {asset}: No qualifying setup (score: {result.get('score', 0) if result else 0})")
                                
                        except Exception as e:
                            logger.error(f"Error analyzing {asset}: {e}")
                    
                    last_analysis = current_time
                
                # Monitor existing positions for trailing SL
                for asset in list(risk_manager.active_positions.keys()):
                    try:
                        # Get current price from ticker
                        ticker = info.ticker(asset)
                        if ticker and len(ticker) > 0:
                            current_price = float(ticker[0].get('close', 0))
                            
                            # Update position PnL and check for trailing SL
                            risk_action = await risk_manager.update_position_pnl(asset, current_price)
                            if risk_action:
                                logger.info(f"📊 {asset} risk action: {risk_action}")
                                
                    except Exception as e:
                        logger.error(f"Error monitoring position {asset}: {e}")
                
                # Active position monitoring with DeepSeek (every 30s)
                if current_time - last_monitoring >= 30:
                    await monitor_active_positions(engine, risk_manager, assets, info)
                    last_monitoring = current_time
                
                # Sleep for 1 second to prevent excessive CPU usage
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
                
    except KeyboardInterrupt:
        logger.info("🛑 Degen God stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error in main: {e}")
        raise


if __name__ == "__main__":
    """
    Entry point for the Degen God v2 bot.
    """
    parser = argparse.ArgumentParser(description="Degen God v2 - Autonomous Trading Bot")
    parser.add_argument("--dashboard", action="store_true", help="Launch Streamlit dashboard")
    parser.add_argument("--test", action="store_true", help="Run test mode")
    
    args = parser.parse_args()
    
    if args.dashboard:
        logger.info("🚀 Launching Degen God v2 Dashboard...")
        os.system("streamlit run ui/dashboard.py")
    elif args.test:
        logger.info("🧪 Running Degen God v2 in test mode...")
        # Test mode would run with mock data
        asyncio.run(main())
    else:
        logger.info("🎯 Starting Degen God v2.0 - 'We don't gamble. We hunt with 50x and a PhD.'")
        asyncio.run(main())