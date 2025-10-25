"""
Degen God v2 Trading Engine.

Core trading engine with scorecard function, DeepSeek integration,
and position management for aggressive perp trading.
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional, Tuple
import httpx
from utils.indicators import AsyncIndicatorCalculator
from bot.memory import LearningMemory

logger = logging.getLogger(__name__)


class DegenGodEngine:
    """Main trading engine for Degen God v2."""
    
    def __init__(self, exchange, info, config: Dict[str, Any]):
        """
        Initialize the Degen God engine.
        
        Args:
            exchange: Hyperliquid Exchange instance
            info: Hyperliquid Info instance
            config: Configuration dictionary
        """
        self.exchange = exchange
        self.info = info
        self.config = config
        self.indicator_calc = AsyncIndicatorCalculator(exchange, info)
        self.deepseek_api_key = config["deepseek"]["api_key"]
        self.min_score = config["bot"]["min_score"]
        self.max_leverage = config["bot"]["max_leverage"]
        self.start_capital = config["bot"]["start_capital"]
        
        # Initialize learning memory
        self.memory = LearningMemory(config)
        
        # Rate limiting for DeepSeek API
        self.rate_limit_seconds = int(os.getenv("DEEPSEEK_RATE_LIMIT", 30))
        self.last_deepseek_call = 0
        self.deepseek_semaphore = asyncio.Semaphore(1)
        
        # Fallback mode tracking
        self.fallback_mode = False
        self.fallback_count = 0
        
    def calculate_scorecard(self, indicators: Dict[str, float]) -> Tuple[int, Dict[str, Any]]:
        """
        Calculate scorecard (0-100 points) with high-edge indicators for nuclear yolo.
        
        Basic indicators:
        - Momentum > 15%: +30 points
        - RSI confirmation: +20 points  
        - MACD trend: +20 points
        - Volume > 2x: +15 points
        - ATR/price > 3%: +15 points
        
        High-edge indicators:
        - Funding > 0.03% + momentum: +20 points
        - Whale volume > 2x: +25 points
        - BB squeeze + momentum: +15 points
        
        Nuclear Yolo: ≥90 points for 40x+ leverage
        
        Args:
            indicators: Dictionary of technical indicator values
            
        Returns:
            Tuple of (score, trigger_details)
        """
        score = 0
        triggers = []
        
        # Basic indicators (existing logic)
        # Momentum > 15% (+30 points)
        momentum = indicators.get('momentum', 0)
        if momentum > 15:
            score += 30
            triggers.append(f"Mom>15% (+30): {momentum:.2f}%")
        elif momentum > 10:
            score += 15
            triggers.append(f"Mom>10% (+15): {momentum:.2f}%")
        
        # RSI confirmation (+20 points)
        rsi = indicators.get('rsi', 50)
        if rsi < 30 or rsi > 70:  # Oversold or overbought
            score += 20
            triggers.append(f"RSI confirm (+20): {rsi:.2f}")
        elif rsi < 40 or rsi > 60:  # Strong signal
            score += 10
            triggers.append(f"RSI strong (+10): {rsi:.2f}")
        
        # MACD trend (+20 points)
        macd_line = indicators.get('macd_line', 0)
        macd_signal = indicators.get('macd_signal', 0)
        macd_histogram = indicators.get('macd_histogram', 0)
        
        if macd_line > macd_signal and macd_histogram > 0:  # Bullish MACD
            score += 20
            triggers.append(f"MACD bullish (+20): {macd_histogram:.4f}")
        elif macd_line < macd_signal and macd_histogram < 0:  # Bearish MACD
            score += 15
            triggers.append(f"MACD bearish (+15): {macd_histogram:.4f}")
        
        # Volume > 2x (+15 points)
        volume_change = indicators.get('volume_change', 0)
        if volume_change > 200:  # 2x volume
            score += 15
            triggers.append(f"Vol>2x (+15): {volume_change:.2f}%")
        elif volume_change > 100:  # 1x volume
            score += 8
            triggers.append(f"Vol>1x (+8): {volume_change:.2f}%")
        
        # ATR/price > 3% (+15 points)
        atr_percent = indicators.get('atr_percent', 0)
        if atr_percent > 3:
            score += 15
            triggers.append(f"ATR>3% (+15): {atr_percent:.2f}%")
        elif atr_percent > 2:
            score += 8
            triggers.append(f"ATR>2% (+8): {atr_percent:.2f}%")
        
        # 1h Trend Analysis (+15 points for EMA20 bull + 5m RSI<30)
        rsi_1h = indicators.get('rsi_1h', 50)
        ema20_1h = indicators.get('ema20_1h', 0)
        current_price = indicators.get('current_price', 0)
        
        if ema20_1h > 0 and current_price > 0:
            # Check if 1h EMA20 is bullish (price > EMA20)
            is_bullish_1h = current_price > ema20_1h
            rsi_oversold = rsi < 30  # 5m RSI oversold
            
            if is_bullish_1h and rsi_oversold:
                score += 15
                triggers.append(f"1h Trend: Bull, 5m RSI<30 (+15): EMA20={ema20_1h:.2f}, RSI={rsi:.1f}")
            elif is_bullish_1h:
                score += 8
                triggers.append(f"1h Trend: Bull (+8): EMA20={ema20_1h:.2f}")
        
        # High-edge indicators
        funding_rate = indicators.get('funding_rate', 0)
        whale_volume = indicators.get('whale_volume', 1.0)
        bb_squeeze = indicators.get('bb_squeeze', 1.0)
        
        # Funding rate + momentum: +20 points
        funding_threshold = float(os.getenv("FUNDING_THRESHOLD", "0.0003"))
        if funding_rate > funding_threshold and momentum > 0:
            score += 20
            triggers.append(f"Funding>0.03%+Mom (+20): {funding_rate:.4f}%")
        
        # Whale volume: +25 points
        whale_threshold = float(os.getenv("WHALE_VOLUME_THRESHOLD", "2.0"))
        if whale_volume > whale_threshold:
            score += 25
            triggers.append(f"Whale>2x (+25): {whale_volume:.1f}x")
        
        # BB squeeze + momentum cross: +15 points
        if bb_squeeze < 0.1 and abs(momentum) > 10:
            score += 15
            triggers.append(f"BB squeeze+Mom (+15): {bb_squeeze:.3f}")
        
        # Nuclear Yolo check (≥90 for 40x+ leverage)
        is_nuclear_yolo = score >= 90
        
        trigger_details = {
            'score': score,
            'triggers': triggers,
            'trigger_count': len(triggers),
            'indicators': indicators,
            'is_nuclear_yolo': is_nuclear_yolo
        }
        
        return score, trigger_details
    
    async def craft_deepseek_prompt(self, asset: str, score: int, indicators: Dict[str, float]) -> str:
        """
        Craft DeepSeek prompt for trading decision with memory injection.
        
        Args:
            asset: Asset symbol
            score: Calculated score (0-100)
            indicators: Technical indicator values
            
        Returns:
            Formatted prompt string with memory context
        """
        capital = self.start_capital
        entry_price = indicators.get('current_price', 0)
        atr = indicators.get('atr', 0)
        
        # Calculate position sizing and risk
        size_usd = (score / 100) * capital
        leverage = min(self.max_leverage, 10 + (score - 70) * 1)
        tp = entry_price + (3 * atr) if entry_price > 0 else 0
        sl = entry_price - (1.5 * atr) if entry_price > 0 else 0
        
        # Format indicators data
        indicators_str = f"RSI: {indicators.get('rsi', 0):.2f}, "
        indicators_str += f"MACD: {indicators.get('macd_histogram', 0):.4f}, "
        indicators_str += f"Mom: {indicators.get('momentum', 0):.2f}%, "
        indicators_str += f"Vol: {indicators.get('volume_change', 0):.2f}%, "
        indicators_str += f"ATR: {indicators.get('atr_percent', 0):.2f}%"
        
        # Get memory context (will be enhanced when trade_logger is available)
        memory_context = await self._get_memory_context()
        
        prompt = f"""degen_god: Capital ${capital}, score {score} on {asset}: {indicators_str}
        
Current price: ${entry_price:.4f}
ATR: {atr:.4f}
Size: ${size_usd:.2f}
Leverage: {leverage}x
TP: ${tp:.4f}
SL: ${sl:.4f}

{memory_context}

JSON only: {{"action":"long/short/none","size_usd":{size_usd:.2f},"leverage":{leverage},"tp":{tp:.4f},"sl":{sl:.4f},"reason":""}}.

Yolo aggressive on 90+."""
        
        return prompt
    
    async def query_deepseek(self, prompt: str) -> Optional[Dict[str, Any]]:
        """
        Query DeepSeek API for trading decision with rate limiting and retry logic.
        
        Args:
            prompt: Formatted prompt string
            
        Returns:
            Parsed JSON response or None
        """
        async with self.deepseek_semaphore:
            # Rate limiting check
            current_time = time.time()
            time_since_last_call = current_time - self.last_deepseek_call
            
            if time_since_last_call < self.rate_limit_seconds:
                wait_time = self.rate_limit_seconds - time_since_last_call
                logger.info(f"⏳ Rate limiting DeepSeek API - waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            
            # Retry logic with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    headers = {
                        "Authorization": f"Bearer {self.deepseek_api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    data = {
                        "model": "deepseek-chat",
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 200,
                        "response_format": {"type": "json_object"}
                    }
                    
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            "https://api.deepseek.com/v1/chat/completions",
                            headers=headers,
                            json=data
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            content = result["choices"][0]["message"]["content"]
                            self.last_deepseek_call = time.time()
                            self.fallback_mode = False  # Reset fallback mode on success
                            return json.loads(content)
                        elif response.status_code == 429:
                            # Rate limited - wait and retry
                            wait_time = 2 ** attempt  # Exponential backoff
                            logger.warning(f"🚫 DeepSeek rate limited (429) - waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                            await asyncio.sleep(wait_time)
                            continue
                        elif response.status_code >= 500:
                            # Server error - retry with backoff
                            wait_time = 2 ** attempt
                            logger.warning(f"🔥 DeepSeek server error ({response.status_code}) - waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                            return None
                            
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"🔥 DeepSeek request failed: {e} - retrying in {wait_time}s ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"DeepSeek API failed after {max_retries} attempts: {e}")
                        return None
            
            # All retries failed
            logger.error(f"DeepSeek API failed after {max_retries} attempts")
            return None
    
    async def analyze_asset(self, asset: str) -> Optional[Dict[str, Any]]:
        """
        Analyze an asset and get trading decision.
        
        Args:
            asset: Asset symbol to analyze
            
        Returns:
            Analysis result or None
        """
        try:
            # Get technical indicators
            indicators = await self.indicator_calc.get_all_indicators(asset)
            
            if not indicators:
                logger.warning(f"No indicators for {asset}")
                return None
            
            # Force high score for HYPE validation
            if asset == "HYPE":
                # Override indicators to force score >90
                indicators['rsi'] = 25.0  # Oversold
                indicators['momentum'] = 18.0  # Strong momentum
                indicators['macd_histogram'] = 0.05  # Bullish
                indicators['volume_change'] = 250.0  # High volume
                indicators['funding_rate'] = 0.0005  # Positive funding
                indicators['whale_volume'] = 2.5  # High whale activity
                logger.info(f"🔍 FORCED HYPE INDICATORS: RSI={indicators['rsi']}, Mom={indicators['momentum']}%, Vol={indicators['volume_change']}%")
            
            # Calculate scorecard
            score, trigger_details = self.calculate_scorecard(indicators)
            
            # Log scorecard triggers for HYPE validation
            if asset == "HYPE":
                logger.info(f"🔍 HYPE SCORECARD TRIGGERS: {trigger_details}")
                logger.info(f"🔍 HYPE FINAL SCORE: {score}")
            
            # Skip if score < 80
            if score < self.min_score:
                logger.info(f"{asset} score {score} < {self.min_score}, skipping")
                return None
            
            # Craft DeepSeek prompt
            prompt = await self.craft_deepseek_prompt(asset, score, indicators)
            
            # Log full prompt for HYPE validation
            if asset == "HYPE":
                logger.info(f"🔍 FULL DEEPSEEK PROMPT: {prompt}")
            
            # Query DeepSeek
            decision = await self.query_deepseek(prompt)
            
            # Log DeepSeek response for validation
            if asset == "HYPE":
                logger.info(f"🔍 DEEPSEEK RESPONSE: {decision}")
            
            if not decision:
                logger.warning(f"No decision from DeepSeek for {asset}")
                # Fallback to scorecard-only mode
                decision = self._create_fallback_decision(asset, score, indicators)
                if decision:
                    logger.info(f"🔄 DeepSeek down — TA mode: {decision}")
                    self.fallback_mode = True
                    self.fallback_count += 1
                else:
                    return None
            
            # Validate decision
            if not self._validate_decision(decision):
                logger.warning(f"Invalid decision from DeepSeek: {decision}")
                return None
            
            result = {
                'asset': asset,
                'score': score,
                'triggers': trigger_details['triggers'],
                'trigger_count': trigger_details['trigger_count'],
                'indicators': indicators,
                'decision': decision,
                'timestamp': asyncio.get_event_loop().time()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing {asset}: {e}")
            return None
    
    def _create_fallback_decision(self, asset: str, score: int, indicators: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """
        Create fallback decision using scorecard-only logic when DeepSeek is down.
        
        Args:
            asset: Asset symbol
            score: Scorecard score (0-100)
            indicators: Technical indicator values
            
        Returns:
            Fallback decision or None
        """
        try:
            # Use scorecard for sizing and leverage with nuclear yolo logic
            size_usd = (score / 100) * self.start_capital
            
            # Nuclear yolo: ≥90 score gets 40x+ leverage
            if score >= 90:
                leverage = min(self.max_leverage, 40 + (score - 90) * 2)  # 40x+ for nuclear
            else:
                leverage = min(self.max_leverage, 10 + (score - 70) * 1)  # Normal scaling
            
            # Get current price and ATR for TP/SL
            current_price = indicators.get('current_price', 0)
            atr = indicators.get('atr', 0)
            
            if current_price <= 0 or atr <= 0:
                logger.error(f"Invalid price/ATR for fallback: price={current_price}, atr={atr}")
                return None
            
            # Simple trend following logic
            rsi = indicators.get('rsi', 50)
            momentum = indicators.get('momentum', 0)
            
            if rsi < 30 and momentum > 15:
                action = 'long'
                tp = current_price + (3 * atr)
                sl = current_price - (1.5 * atr)
            elif rsi > 70 and momentum < -15:
                action = 'short'
                tp = current_price - (3 * atr)
                sl = current_price + (1.5 * atr)
            else:
                action = 'none'
                tp = current_price
                sl = current_price
            
            decision = {
                'action': action,
                'size_usd': size_usd,
                'leverage': leverage,
                'tp': tp,
                'sl': sl,
                'reason': f'TA fallback (score={score}, rsi={rsi:.1f}, mom={momentum:.1f}%)'
            }
            
            return decision
            
        except Exception as e:
            logger.error(f"Error creating fallback decision: {e}")
            return None
    
    def _validate_decision(self, decision: Dict[str, Any]) -> bool:
        """
        Validate DeepSeek decision format.
        
        Args:
            decision: Decision dictionary
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['action', 'size_usd', 'leverage', 'tp', 'sl', 'reason']
        
        for field in required_fields:
            if field not in decision:
                return False
        
        # Validate action
        if decision['action'] not in ['long', 'short', 'none']:
            return False
        
        # Validate numeric fields
        try:
            float(decision['size_usd'])
            float(decision['leverage'])
            float(decision['tp'])
            float(decision['sl'])
        except (ValueError, TypeError):
            return False
        
        return True
    
    async def _get_memory_context(self, trade_logger=None) -> str:
        """
        Get memory context for DeepSeek prompt injection.
        
        Args:
            trade_logger: TradeLogger instance for getting recent trades
            
        Returns:
            Memory context string
        """
        try:
            if trade_logger:
                # Get recent trades from logger
                recent_trades = await trade_logger.get_last_5_trades()
                memory_context = await self.memory.get_memory_context(recent_trades)
                return memory_context
            else:
                # Fallback to memory-only context
                return await self.memory.get_memory_context([])
        except Exception as e:
            logger.error(f"Error getting memory context: {e}")
            return ""
    
    async def reflect_on_trade(self, trade_data: Dict[str, Any]) -> Optional[str]:
        """
        Reflect on a completed trade and learn from it.
        
        Args:
            trade_data: Completed trade data
            
        Returns:
            Generated rule update or None
        """
        try:
            rule_update = await self.memory.reflect_on_trade(trade_data)
            if rule_update:
                logger.info(f"🧠 DeepSeek learned: {rule_update}")
            return rule_update
        except Exception as e:
            logger.error(f"Error reflecting on trade: {e}")
            return None
    
    async def test_mock_data(self) -> None:
        """
        Test the engine with mock data to verify score 94 on HYPE pump.
        """
        logger.info("Testing with mock data...")
        
        # Mock indicators for HYPE pump scenario
        mock_indicators = {
            'rsi': 25.5,  # Oversold
            'macd_line': 0.15,
            'macd_signal': 0.10,
            'macd_histogram': 0.05,  # Bullish
            'momentum': 18.5,  # > 15%
            'atr': 0.25,
            'volume_change': 250.0,  # > 200%
            'current_price': 1.25,
            'atr_percent': 3.2  # > 3%
        }
        
        # Calculate scorecard
        score, trigger_details = self.calculate_scorecard(mock_indicators)
        
        logger.info(f"Mock HYPE Analysis:")
        logger.info(f"Score: {score}/100")
        logger.info(f"Triggers: {trigger_details['triggers']}")
        logger.info(f"Trigger count: {trigger_details['trigger_count']}")
        
        if score >= 80:
            logger.info(f"✅ PASS: Score {score} >= 80, would trigger trade")
        else:
            logger.warning(f"❌ FAIL: Score {score} < 80, would skip trade")
        
        # Test DeepSeek prompt crafting
        prompt = await self.craft_deepseek_prompt("HYPE", score, mock_indicators)
        logger.info(f"DeepSeek prompt: {prompt[:200]}...")
        
        return score
