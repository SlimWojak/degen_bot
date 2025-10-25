"""
Learning Loop 0.1 - Self-evaluation and reflection engine.
Analyzes past trades and market outcomes to improve future decisions.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("learning_loop")

@dataclass
class Reflection:
    """Structured reflection on trading performance."""
    timestamp: str
    period: str  # "hourly", "daily", "weekly"
    trades_analyzed: int
    performance_score: float  # -1.0 to 1.0
    key_insights: List[str]
    recommendations: List[str]
    reflection_text: str

class LearningLoop:
    """Learning loop for self-evaluation and improvement."""
    
    def __init__(self):
        self.reflection_log_path = f"data/reflections-{datetime.now().strftime('%Y-%m-%d')}.json"
        self.analysis_window_hours = 24  # Analyze last 24 hours
        self.min_trades_for_reflection = 3
        
        # Ensure data directory exists
        os.makedirs("data", exist_ok=True)
    
    async def reflect(self, symbol: str = "BTC") -> Dict[str, Any]:
        """
        Perform reflection on recent trading performance.
        
        Args:
            symbol: Symbol to analyze (default: BTC)
            
        Returns:
            Reflection results with insights and recommendations
        """
        try:
            # Get recent trades
            recent_trades = await self._get_recent_trades(symbol)
            
            if len(recent_trades) < self.min_trades_for_reflection:
                return {
                    "status": "insufficient_data",
                    "message": f"Need at least {self.min_trades_for_reflection} trades for reflection",
                    "trades_analyzed": len(recent_trades)
                }
            
            # Analyze performance
            performance_analysis = await self._analyze_performance(recent_trades)
            
            # Generate insights
            insights = await self._generate_insights(performance_analysis, recent_trades)
            
            # Create reflection
            reflection = Reflection(
                timestamp=datetime.now(timezone.utc).isoformat(),
                period="hourly",
                trades_analyzed=len(recent_trades),
                performance_score=performance_analysis["score"],
                key_insights=insights["insights"],
                recommendations=insights["recommendations"],
                reflection_text=insights["reflection_text"]
            )
            
            # Log reflection
            await self._log_reflection(reflection)
            
            logger.info(f"[learning_loop] Reflection completed: {len(recent_trades)} trades, score: {performance_analysis['score']:.2f}")
            
            return {
                "status": "completed",
                "reflection": reflection.__dict__,
                "performance_analysis": performance_analysis
            }
            
        except Exception as e:
            logger.error(f"[learning_loop] Reflection failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def _get_recent_trades(self, symbol: str) -> List[Dict[str, Any]]:
        """Get recent trades for analysis."""
        try:
            # Read from trade log
            trade_log_path = f"data/positions-log-{datetime.now().strftime('%Y-%m-%d')}.json"
            
            if not os.path.exists(trade_log_path):
                return []
            
            trades = []
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.analysis_window_hours)
            
            with open(trade_log_path, "r") as f:
                for line in f:
                    if line.strip():
                        trade = json.loads(line)
                        if trade.get("symbol") == symbol:
                            trade_time = datetime.fromisoformat(trade["timestamp"].replace("Z", "+00:00"))
                            if trade_time >= cutoff_time:
                                trades.append(trade)
            
            return trades
            
        except Exception as e:
            logger.error(f"[learning_loop] Failed to get recent trades: {e}")
            return []
    
    async def _analyze_performance(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trading performance."""
        if not trades:
            return {"score": 0.0, "trades": 0, "win_rate": 0.0}
        
        # Simple performance metrics
        total_trades = len(trades)
        executed_trades = [t for t in trades if t.get("status") == "executed"]
        
        # Mock performance calculation (in real implementation, would track P&L)
        win_rate = 0.6  # Mock 60% win rate
        avg_confidence = sum(t.get("confidence", 0.5) for t in executed_trades) / len(executed_trades) if executed_trades else 0.5
        
        # Calculate performance score (-1.0 to 1.0)
        performance_score = (win_rate - 0.5) * 2  # Convert 0-1 to -1 to 1
        
        return {
            "score": performance_score,
            "trades": total_trades,
            "executed": len(executed_trades),
            "win_rate": win_rate,
            "avg_confidence": avg_confidence
        }
    
    async def _generate_insights(self, performance: Dict[str, Any], trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate insights and recommendations."""
        score = performance["score"]
        win_rate = performance["win_rate"]
        avg_confidence = performance["avg_confidence"]
        
        insights = []
        recommendations = []
        
        # Performance-based insights
        if score > 0.3:
            insights.append("Strong positive performance detected")
            recommendations.append("Consider increasing position sizes gradually")
        elif score < -0.3:
            insights.append("Negative performance trend detected")
            recommendations.append("Reduce position sizes and review strategy")
        else:
            insights.append("Neutral performance - room for improvement")
            recommendations.append("Focus on improving signal quality")
        
        # Confidence-based insights
        if avg_confidence > 0.8:
            insights.append("High confidence trades performing well")
            recommendations.append("Maintain current confidence thresholds")
        elif avg_confidence < 0.6:
            insights.append("Low confidence trades may be causing issues")
            recommendations.append("Increase minimum confidence threshold")
        
        # Trade frequency insights
        if len(trades) > 10:
            insights.append("High trading frequency detected")
            recommendations.append("Consider longer cooldown periods")
        elif len(trades) < 5:
            insights.append("Low trading frequency")
            recommendations.append("Review signal generation and confidence thresholds")
        
        # Generate reflection text
        reflection_text = f"""
Trading Performance Reflection:

Period: Last {len(trades)} trades
Performance Score: {score:.2f} ({'Positive' if score > 0 else 'Negative' if score < 0 else 'Neutral'})
Win Rate: {win_rate:.1%}
Average Confidence: {avg_confidence:.2f}

Key Insights:
{chr(10).join(f"- {insight}" for insight in insights)}

Recommendations:
{chr(10).join(f"- {rec}" for rec in recommendations)}

This reflection will help improve future trading decisions.
"""
        
        return {
            "insights": insights,
            "recommendations": recommendations,
            "reflection_text": reflection_text.strip()
        }
    
    async def _log_reflection(self, reflection: Reflection) -> None:
        """Log reflection to daily file."""
        try:
            log_entry = {
                "timestamp": reflection.timestamp,
                "period": reflection.period,
                "trades_analyzed": reflection.trades_analyzed,
                "performance_score": reflection.performance_score,
                "key_insights": reflection.key_insights,
                "recommendations": reflection.recommendations,
                "reflection_text": reflection.reflection_text
            }
            
            # Append to daily log file
            with open(self.reflection_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
                
        except Exception as e:
            logger.error(f"[learning_loop] Failed to log reflection: {e}")
    
    def get_reflection_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get reflection history from log file."""
        try:
            if not os.path.exists(self.reflection_log_path):
                return []
            
            history = []
            with open(self.reflection_log_path, "r") as f:
                for line in f:
                    if line.strip():
                        reflection = json.loads(line)
                        history.append(reflection)
            
            return history[-limit:] if history else []
            
        except Exception as e:
            logger.error(f"[learning_loop] Failed to get reflection history: {e}")
            return []
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        try:
            reflections = self.get_reflection_history(10)
            
            if not reflections:
                return {
                    "total_reflections": 0,
                    "avg_performance_score": 0.0,
                    "trend": "neutral"
                }
            
            scores = [r.get("performance_score", 0.0) for r in reflections]
            avg_score = sum(scores) / len(scores)
            
            # Determine trend
            if len(scores) >= 3:
                recent_avg = sum(scores[-3:]) / 3
                if recent_avg > avg_score + 0.1:
                    trend = "improving"
                elif recent_avg < avg_score - 0.1:
                    trend = "declining"
                else:
                    trend = "stable"
            else:
                trend = "insufficient_data"
            
            return {
                "total_reflections": len(reflections),
                "avg_performance_score": avg_score,
                "trend": trend,
                "latest_score": scores[-1] if scores else 0.0
            }
            
        except Exception as e:
            logger.error(f"[learning_loop] Failed to get performance summary: {e}")
            return {
                "total_reflections": 0,
                "avg_performance_score": 0.0,
                "trend": "error"
            }

# Global learning loop instance
learning_loop = LearningLoop()
