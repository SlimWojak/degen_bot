"""
Reasoning Engine - Transform raw sampler data into interpretable signals.
Core thinking module that analyzes market data and produces structured insights.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("reasoning_engine")

@dataclass
class MarketSignal:
    """Structured market signal from analysis."""
    symbol: str
    trend_bias: str  # "bullish", "bearish", "neutral"
    confidence: float  # 0.0 to 1.0
    rationale: str
    key_indicators: Dict[str, Any]
    timestamp: str

class ReasoningEngine:
    """Core reasoning engine that analyzes market data and produces insights."""
    
    def __init__(self):
        self.analysis_cache: List[MarketSignal] = []
        self.max_cache_size = 50
        self.llm_provider = os.getenv("LLM_PROVIDER", "mock")
        self.analysis_log_path = f"data/reasoning-log-{datetime.now().strftime('%Y-%m-%d')}.json"
        
        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)
    
    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze market context and produce structured insights.
        
        Args:
            context: Market data from sampler (prices, funding, OI, volume, etc.)
            
        Returns:
            Structured analysis with trend bias, confidence, and rationale
        """
        try:
            # Extract key market indicators
            indicators = self._extract_indicators(context)
            
            # Generate reasoning prompt
            prompt = self._build_reasoning_prompt(indicators)
            
            # Get LLM analysis (mock for now)
            analysis = await self._llm_reason(prompt)
            
            # Create structured signal
            signal = MarketSignal(
                symbol=indicators.get("symbol", "BTC"),
                trend_bias=analysis.get("trend_bias", "neutral"),
                confidence=analysis.get("confidence", 0.5),
                rationale=analysis.get("rationale", "No clear signal detected"),
                key_indicators=indicators,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
            # Cache the analysis
            self._cache_analysis(signal)
            
            # Log to file
            await self._log_analysis(signal)
            
            logger.info(f"[reasoning] {signal.symbol} {signal.trend_bias} (conf: {signal.confidence:.2f})")
            
            return {
                "symbol": signal.symbol,
                "trend_bias": signal.trend_bias,
                "confidence": signal.confidence,
                "rationale": signal.rationale,
                "key_indicators": signal.key_indicators,
                "timestamp": signal.timestamp
            }
            
        except Exception as e:
            logger.error(f"[reasoning] Analysis failed: {e}")
            return {
                "symbol": "BTC",
                "trend_bias": "neutral",
                "confidence": 0.0,
                "rationale": f"Analysis error: {str(e)}",
                "key_indicators": {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _extract_indicators(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key market indicators from context."""
        indicators = {
            "symbol": context.get("symbol", "BTC"),
            "price": context.get("price", 0),
            "price_change_24h": context.get("price_change_24h", 0),
            "funding_rate": context.get("funding_rate", 0),
            "open_interest": context.get("open_interest", 0),
            "volume_24h": context.get("volume_24h", 0),
            "spread_bps": context.get("spread_bps", 0),
            "last_update": context.get("last_update")
        }
        
        # Calculate derived indicators
        if indicators["price"] > 0:
            indicators["price_change_pct"] = (indicators["price_change_24h"] / indicators["price"]) * 100
        else:
            indicators["price_change_pct"] = 0
            
        return indicators
    
    def _build_reasoning_prompt(self, indicators: Dict[str, Any]) -> str:
        """Build reasoning prompt for LLM analysis."""
        symbol = indicators.get("symbol", "BTC")
        price = indicators.get("price", 0)
        price_change_pct = indicators.get("price_change_pct", 0)
        funding_rate = indicators.get("funding_rate", 0)
        open_interest = indicators.get("open_interest", 0)
        volume_24h = indicators.get("volume_24h", 0)
        
        prompt = f"""
Analyze the following market data for {symbol} and provide a structured assessment:

Price: ${price:,.2f} ({price_change_pct:+.2f}% 24h)
Funding Rate: {funding_rate:.4f}
Open Interest: {open_interest:,.0f}
Volume 24h: {volume_24h:,.0f}

Provide analysis in JSON format:
{{
    "trend_bias": "bullish|bearish|neutral",
    "confidence": 0.0-1.0,
    "rationale": "Brief explanation of the reasoning",
    "key_factors": ["factor1", "factor2", "factor3"]
}}

Consider:
- Price momentum and trend
- Funding rate implications
- Open interest changes
- Volume patterns
- Market structure signals
"""
        return prompt
    
    async def _llm_reason(self, prompt: str) -> Dict[str, Any]:
        """Get LLM reasoning analysis (mock implementation)."""
        if self.llm_provider == "mock":
            return await self._mock_llm_reason(prompt)
        elif self.llm_provider == "openai":
            return await self._openai_reason(prompt)
        else:
            return await self._mock_llm_reason(prompt)
    
    async def _mock_llm_reason(self, prompt: str) -> Dict[str, Any]:
        """Mock LLM reasoning for development."""
        # Simple rule-based analysis for now
        import random
        
        # Extract some basic signals from prompt
        if "funding" in prompt.lower() and "positive" in prompt.lower():
            trend_bias = "bullish"
            confidence = 0.7
            rationale = "Positive funding suggests bullish sentiment"
        elif "funding" in prompt.lower() and "negative" in prompt.lower():
            trend_bias = "bearish"
            confidence = 0.7
            rationale = "Negative funding suggests bearish sentiment"
        else:
            trend_bias = random.choice(["bullish", "bearish", "neutral"])
            confidence = random.uniform(0.3, 0.8)
            rationale = f"Mixed signals detected, leaning {trend_bias}"
        
        return {
            "trend_bias": trend_bias,
            "confidence": confidence,
            "rationale": rationale,
            "key_factors": ["price_momentum", "funding_rate", "volume"]
        }
    
    async def _openai_reason(self, prompt: str) -> Dict[str, Any]:
        """OpenAI LLM reasoning (placeholder for future implementation)."""
        # TODO: Implement OpenAI API call
        logger.warning("[reasoning] OpenAI provider not implemented, using mock")
        return await self._mock_llm_reason(prompt)
    
    def _cache_analysis(self, signal: MarketSignal) -> None:
        """Cache the latest analysis."""
        self.analysis_cache.append(signal)
        if len(self.analysis_cache) > self.max_cache_size:
            self.analysis_cache.pop(0)
    
    async def _log_analysis(self, signal: MarketSignal) -> None:
        """Log analysis to daily file."""
        try:
            log_entry = {
                "timestamp": signal.timestamp,
                "symbol": signal.symbol,
                "trend_bias": signal.trend_bias,
                "confidence": signal.confidence,
                "rationale": signal.rationale,
                "key_indicators": signal.key_indicators
            }
            
            # Append to daily log file
            with open(self.analysis_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            logger.error(f"[reasoning] Failed to log analysis: {e}")
    
    def get_latest_analysis(self, symbol: str = "BTC") -> Optional[MarketSignal]:
        """Get the latest analysis for a symbol."""
        for signal in reversed(self.analysis_cache):
            if signal.symbol == symbol:
                return signal
        return None
    
    def get_analysis_history(self, symbol: str = "BTC", limit: int = 10) -> List[MarketSignal]:
        """Get analysis history for a symbol."""
        history = [s for s in self.analysis_cache if s.symbol == symbol]
        return history[-limit:] if history else []

# Global reasoning engine instance
reasoning_engine = ReasoningEngine()
