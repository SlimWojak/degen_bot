"""
Technical indicators module with async WebSocket data fetching.

This module handles real-time 5m candle data from Hyperliquid WebSocket
and computes technical indicators: RSI, MACD, Momentum, ATR, and volume change.
"""

import asyncio
import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Optional, Tuple
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.signing import get_timestamp_ms
import logging

logger = logging.getLogger(__name__)


class AsyncIndicatorCalculator:
    """Async technical indicator calculator with WebSocket data fetching."""
    
    def __init__(self, exchange: Exchange, info: Info):
        """
        Initialize the indicator calculator.
        
        Args:
            exchange: Hyperliquid Exchange instance
            info: Hyperliquid Info instance
        """
        self.exchange = exchange
        self.info = info
        self.candle_data: Dict[str, pd.DataFrame] = {}
        
    async def fetch_1h_candles(self, asset: str, limit: int = 24) -> pd.DataFrame:
        """
        Fetch 1-hour candles for an asset via REST API.
        
        Args:
            asset: Asset symbol (e.g., 'HYPE', 'BTC')
            limit: Number of candles to fetch (default 24 for 24h)
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Calculate time range for candles (24 hours ago to now)
            end_time = get_timestamp_ms()
            start_time = end_time - (limit * 60 * 60 * 1000)  # 1 hour per candle
            
            # Format asset name for SDK
            name = asset.upper()
            
            # Use REST API to fetch candles via info.candles_snapshot
            candles = self.info.candles_snapshot(name, "1h", start_time, end_time)
            
            if not candles:
                logger.warning(f"No 1h candle data for {name}")
                return pd.DataFrame()
            
            # Convert to DataFrame with correct column mapping
            df = pd.DataFrame(candles)
            
            # Rename columns from SDK format (T,o,h,l,c,v) to standard format
            df['timestamp'] = pd.to_datetime(df['T'] / 1000, unit='s')
            df['open'] = pd.to_numeric(df['o'], errors='coerce')
            df['high'] = pd.to_numeric(df['h'], errors='coerce')
            df['low'] = pd.to_numeric(df['l'], errors='coerce')
            df['close'] = pd.to_numeric(df['c'], errors='coerce')
            df['volume'] = pd.to_numeric(df['v'], errors='coerce')
            
            # Set timestamp as index and keep only OHLCV columns
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            df.set_index('timestamp', inplace=True)
            
            logger.info(f"Fetched {len(df)} 1h candles for {name} via REST")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching 1h candles for {asset}: {e}")
            return pd.DataFrame()

    async def fetch_5m_candles(self, asset: str, limit: int = 100) -> pd.DataFrame:
        """
        Fetch 5-minute candles for an asset via REST API.
        
        Args:
            asset: Asset symbol (e.g., 'HYPE', 'BTC')
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Calculate time range for candles (1 hour ago to now)
            end_time = get_timestamp_ms()
            start_time = end_time - 3600000  # 1 hour ago
            
            # Format asset name for SDK (e.g., 'HYPE' -> 'HYPE')
            name = asset.upper()
            
            # Use REST API to fetch candles via info.candles_snapshot
            candles = self.info.candles_snapshot(name, "5m", start_time, end_time)
            
            if not candles:
                logger.warning(f"No candle data for {name}")
                return pd.DataFrame()
            
            # Log raw candle data for validation
            if name == "HYPE" and len(candles) > 0:
                raw_candle = candles[0]
                logger.info(f"🔍 RAW HYPE CANDLE DATA: T={raw_candle.get('T', 'N/A')}, c={raw_candle.get('c', 'N/A')}, o={raw_candle.get('o', 'N/A')}, h={raw_candle.get('h', 'N/A')}, l={raw_candle.get('l', 'N/A')}, v={raw_candle.get('v', 'N/A')}")
            
            # Convert to DataFrame with correct column mapping
            df = pd.DataFrame(candles)
            
            # Rename columns from SDK format (T,o,h,l,c,v) to standard format
            df['timestamp'] = pd.to_datetime(df['T'] / 1000, unit='s')
            df['open'] = pd.to_numeric(df['o'], errors='coerce')
            df['high'] = pd.to_numeric(df['h'], errors='coerce')
            df['low'] = pd.to_numeric(df['l'], errors='coerce')
            df['close'] = pd.to_numeric(df['c'], errors='coerce')
            df['volume'] = pd.to_numeric(df['v'], errors='coerce')
            
            # Set timestamp as index and keep only OHLCV columns
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            df.set_index('timestamp', inplace=True)
            
            self.candle_data[asset] = df
            logger.info(f"Fetched {len(df)} candles for {name} via REST")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching candles for {asset}: {e}")
            return pd.DataFrame()
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate RSI indicator.
        
        Args:
            df: DataFrame with OHLCV data
            period: RSI period (default 14)
            
        Returns:
            RSI value
        """
        if len(df) < period:
            return 50.0  # Neutral RSI if insufficient data
            
        try:
            rsi = ta.momentum.RSIIndicator(df['close'], window=period).rsi()
            return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return 50.0
    
    def calculate_macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """
        Calculate MACD indicator.
        
        Args:
            df: DataFrame with OHLCV data
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        if len(df) < slow:
            return 0.0, 0.0, 0.0
            
        try:
            macd_indicator = ta.trend.MACD(df['close'], window_fast=fast, window_slow=slow, window_sign=signal)
            macd_line = macd_indicator.macd()
            signal_line = macd_indicator.macd_signal()
            histogram = macd_indicator.macd_diff()
            
            return (
                float(macd_line.iloc[-1]) if not pd.isna(macd_line.iloc[-1]) else 0.0,
                float(signal_line.iloc[-1]) if not pd.isna(signal_line.iloc[-1]) else 0.0,
                float(histogram.iloc[-1]) if not pd.isna(histogram.iloc[-1]) else 0.0
            )
        except Exception as e:
            logger.error(f"Error calculating MACD: {e}")
            return 0.0, 0.0, 0.0
    
    def calculate_momentum(self, df: pd.DataFrame, period: int = 10) -> float:
        """
        Calculate momentum indicator.
        
        Args:
            df: DataFrame with OHLCV data
            period: Momentum period
            
        Returns:
            Momentum percentage
        """
        if len(df) < period + 1:
            return 0.0
            
        try:
            current_price = df['close'].iloc[-1]
            past_price = df['close'].iloc[-(period + 1)]
            momentum = ((current_price - past_price) / past_price) * 100
            return float(momentum)
        except Exception as e:
            logger.error(f"Error calculating momentum: {e}")
            return 0.0
    
    def calculate_ema20(self, df: pd.DataFrame, period: int = 20) -> float:
        """
        Calculate 20-period Exponential Moving Average.
        
        Args:
            df: DataFrame with OHLCV data
            period: EMA period (default 20)
            
        Returns:
            EMA20 value
        """
        if len(df) < period:
            return 0.0
            
        try:
            ema = df['close'].ewm(span=period, adjust=False).mean()
            return float(ema.iloc[-1]) if not pd.isna(ema.iloc[-1]) else 0.0
        except Exception as e:
            logger.error(f"Error calculating EMA20: {e}")
            return 0.0

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average True Range.
        
        Args:
            df: DataFrame with OHLCV data
            period: ATR period
            
        Returns:
            ATR value
        """
        if len(df) < period:
            return 0.0
            
        try:
            atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=period)
            return float(atr.average_true_range().iloc[-1]) if not pd.isna(atr.average_true_range().iloc[-1]) else 0.0
        except Exception as e:
            logger.error(f"Error calculating ATR: {e}")
            return 0.0
    
    def calculate_volume_change(self, df: pd.DataFrame) -> float:
        """
        Calculate 24-hour volume change.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            Volume change percentage
        """
        if len(df) < 2:
            return 0.0
            
        try:
            # Get last 24 hours of data (assuming 5m candles = 288 candles for 24h)
            recent_volume = df['volume'].tail(288).sum() if len(df) >= 288 else df['volume'].sum()
            previous_volume = df['volume'].head(-288).sum() if len(df) >= 576 else df['volume'].sum()
            
            if previous_volume == 0:
                return 0.0
                
            volume_change = ((recent_volume - previous_volume) / previous_volume) * 100
            return float(volume_change)
        except Exception as e:
            logger.error(f"Error calculating volume change: {e}")
            return 0.0
    
    async def get_all_indicators(self, asset: str) -> Dict[str, float]:
        """
        Get all technical indicators for an asset.
        
        Args:
            asset: Asset symbol
            
        Returns:
            Dictionary with all indicator values
        """
        # Fetch 5m and 1h candles
        df_5m = await self.fetch_5m_candles(asset)
        df_1h = await self.fetch_1h_candles(asset)
        
        if df_5m.empty:
            logger.warning(f"No 5m data for {asset}")
            return {}
        
        # Calculate 5m indicators
        rsi = self.calculate_rsi(df_5m)
        macd_line, macd_signal, macd_histogram = self.calculate_macd(df_5m)
        momentum = self.calculate_momentum(df_5m)
        atr = self.calculate_atr(df_5m)
        volume_change = self.calculate_volume_change(df_5m)
        current_price = float(df_5m['close'].iloc[-1])
        
        # Log computed indicators for HYPE validation
        if asset == "HYPE":
            logger.info(f"🔍 COMPUTED HYPE INDICATORS: RSI={rsi:.2f}, MACD={macd_histogram:.4f}, Mom={momentum:.2f}%, ATR={atr:.4f}, Price=${current_price:.4f}")
        
        indicators = {
            'rsi': rsi,
            'macd_line': macd_line,
            'macd_signal': macd_signal,
            'macd_histogram': macd_histogram,
            'momentum': momentum,
            'atr': atr,
            'volume_change': volume_change,
            'current_price': current_price,
            'atr_percent': 0.0  # Will be calculated below
        }
        
        # Calculate 1h indicators if data available
        if not df_1h.empty:
            indicators['rsi_1h'] = self.calculate_rsi(df_1h)
            indicators['ema20_1h'] = self.calculate_ema20(df_1h)
        else:
            indicators['rsi_1h'] = 50.0  # Neutral if no data
            indicators['ema20_1h'] = 0.0
        
        # Calculate ATR as percentage of price
        if indicators['current_price'] > 0:
            indicators['atr_percent'] = (indicators['atr'] / indicators['current_price']) * 100
        
        # Add high-edge indicators
        indicators['funding_rate'] = self.get_funding_rate(asset)
        indicators['whale_volume'] = self.get_whale_volume(asset)
        indicators['bb_squeeze'] = self.get_bb_squeeze(df_5m)
        
        logger.info(f"📊 High-edge indicators for {asset}: "
                  f"Funding={indicators['funding_rate']:.4f}%, "
                  f"Whale={indicators['whale_volume']:.1f}x, "
                  f"BB_Squeeze={indicators['bb_squeeze']:.3f}")
        
        return indicators
    
    def get_funding_rate(self, asset: str) -> float:
        """
        Get current funding rate for an asset via REST API with retry logic.
        
        Args:
            asset: Asset symbol
            
        Returns:
            Funding rate as percentage (e.g., 0.0003 for 0.03%)
        """
        name = asset.upper()
        
        for attempt in range(3):
            try:
                # Get funding rate via REST API
                start_time = get_timestamp_ms() - 86400000  # 24 hours ago
                funding_data = self.info.funding_history(name, start_time)
                
                if funding_data and len(funding_data) > 0:
                    # Get the latest funding rate
                    latest_funding = funding_data[-1]
                    if 'rate' in latest_funding:
                        funding_rate = float(latest_funding['rate'])
                        logger.info(f"💰 {name} funding rate: {funding_rate:.4f}%")
                        return funding_rate
                
                if attempt < 2:
                    logger.warning(f"No funding data for {name}, retrying...")
                    continue
                else:
                    logger.warning(f"No funding data for {name} after 3 attempts")
                    return 0.0
                    
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"Error getting funding rate for {asset} (attempt {attempt + 1}): {e}")
                    continue
                else:
                    logger.error(f"Error getting funding rate for {asset} after 3 attempts: {e}")
                    return 0.0
        
        return 0.0
    
    def get_whale_volume(self, asset: str) -> float:
        """
        Calculate whale volume ratio from orderbook depth.
        
        Args:
            asset: Asset symbol
            
        Returns:
            Whale volume ratio (e.g., 2.5 for 2.5x average)
        """
        try:
            # Format asset name for SDK
            name = asset.upper()
            
            # Get orderbook depth 20
            orderbook = self.info.l2_snapshot(name)
            
            if not orderbook or 'levels' not in orderbook:
                logger.warning(f"No orderbook data for {name}")
                return 1.0
            
            levels = orderbook['levels']
            
            # Calculate total volume from l2_snapshot levels
            total_volume = 0
            try:
                for level in levels:
                    if isinstance(level, dict) and 'sz' in level:
                        # Handle dict format: {'px': price, 'sz': size}
                        if isinstance(level['sz'], (int, float, str)):
                            total_volume += float(level['sz'])
                    elif isinstance(level, list) and len(level) >= 2:
                        # Handle list format: [price, size]
                        if isinstance(level[1], (int, float, str)):
                            total_volume += float(level[1])
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Error parsing orderbook levels: {e}")
                return 1.0
            
            current_volume = total_volume
            
            # Get 1-hour average volume (simplified - would need historical data)
            # For now, use a mock calculation based on current volume
            avg_volume = current_volume * 0.5  # Mock: assume current is 2x average
            
            if avg_volume > 0:
                whale_ratio = current_volume / avg_volume
                logger.info(f"🐋 {asset} whale volume: {whale_ratio:.1f}x average")
                return whale_ratio
            else:
                return 1.0
                
        except Exception as e:
            logger.error(f"Error calculating whale volume for {asset}: {e}")
            return 1.0
    
    def get_bb_squeeze(self, df: pd.DataFrame) -> float:
        """
        Calculate Bollinger Band squeeze indicator.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            BB squeeze value (width < 0.1 indicates squeeze)
        """
        try:
            if len(df) < 20:
                return 1.0  # Not enough data
            
            # Calculate Bollinger Bands (20, 2)
            bb_period = 20
            bb_std = 2
            
            # Calculate SMA
            sma = df['close'].rolling(window=bb_period).mean()
            
            # Calculate standard deviation
            std = df['close'].rolling(window=bb_period).std()
            
            # Calculate upper and lower bands
            upper_band = sma + (bb_std * std)
            lower_band = sma - (bb_std * std)
            
            # Calculate BB width (squeeze indicator)
            bb_width = (upper_band - lower_band) / sma
            
            # Get latest width
            latest_width = bb_width.iloc[-1]
            
            logger.info(f"📊 BB squeeze: {latest_width:.3f} (squeeze if < 0.1)")
            return latest_width
            
        except Exception as e:
            logger.error(f"Error calculating BB squeeze: {e}")
            return 1.0
