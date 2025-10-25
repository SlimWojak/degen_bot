"""
Reflection and scoring system for DeepSeek decisions.
Tracks performance and generates evaluation summaries.
"""

import json
import os
import time
import math
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from backend.services.sim_broker import get_sim_broker
from backend.observability.logs import get_recent_decisions

logger = logging.getLogger(__name__)

class ReflectionSystem:
    """Reflection and scoring system for AI decisions."""
    
    def __init__(self):
        self.log_dir = "logs/reflection"
        os.makedirs(self.log_dir, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y-%m-%d")
        self.log_file = os.path.join(self.log_dir, f"{self.session_id}.jsonl")
        self.last_reflection_trade_count = 0
    
    def check_and_generate_reflection(self) -> Optional[Dict[str, Any]]:
        """
        Check if reflection should be generated (every 10 trades).
        
        Returns:
            Reflection summary if generated, None otherwise
        """
        try:
            sim_broker = get_sim_broker()
            metrics = sim_broker.get_metrics()
            current_trades = metrics["trades"]
            
            # Check if we've crossed a 10-trade boundary
            if current_trades >= 10 and current_trades > self.last_reflection_trade_count:
                # Generate reflection
                reflection = self._generate_reflection(current_trades)
                
                # Update counter
                self.last_reflection_trade_count = current_trades
                
                # Persist reflection
                self._persist_reflection(reflection)
                
                return reflection
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to check reflection: {e}")
            return None
    
    def _generate_reflection(self, trade_count: int) -> Dict[str, Any]:
        """Generate reflection summary for recent trades."""
        try:
            sim_broker = get_sim_broker()
            metrics = sim_broker.get_metrics()
            
            # Get recent decisions
            recent_decisions = get_recent_decisions(10)
            filled_decisions = [d for d in recent_decisions if d.get("result") == "filled"]
            
            # Calculate metrics
            trades = metrics["trades"]
            win_rate = metrics["win_rate"]
            realized_pnl = metrics["realized_pnl_usd"]
            unrealized_pnl = metrics["unrealized_pnl_usd"]
            total_pnl = realized_pnl + unrealized_pnl
            avg_slippage = metrics["avg_slippage_bps"]
            
            # Calculate average trade notional
            avg_notional = 0.0
            if filled_decisions:
                total_notional = sum(d.get("notional", 0) for d in filled_decisions)
                avg_notional = total_notional / len(filled_decisions)
            
            # Calculate policy score using sigmoid
            if avg_notional > 0:
                pnl_ratio = total_pnl / avg_notional if avg_notional > 0 else 0
                policy_score = self._sigmoid((pnl_ratio * 20))
            else:
                policy_score = 0.5  # Neutral score
            
            # Generate summary text
            wins = int(trades * win_rate / 100) if trades > 0 else 0
            losses = trades - wins
            
            summary_text = (
                f"Last {trades} trades: {wins}W/{losses}L, "
                f"{total_pnl:+.1f}%, avg_slip {avg_slippage:.0f}bps, "
                f"avg_notional ${avg_notional:.1f}"
            )
            
            reflection = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trades": trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "realized_pnl_usd": realized_pnl,
                "unrealized_pnl_usd": unrealized_pnl,
                "total_pnl_usd": total_pnl,
                "avg_slippage_bps": avg_slippage,
                "avg_notional_usd": avg_notional,
                "policy_score": policy_score,
                "summary_text": summary_text
            }
            
            logger.info(f"Generated reflection: {summary_text}")
            return reflection
            
        except Exception as e:
            logger.error(f"Failed to generate reflection: {e}")
            return {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "realized_pnl_usd": 0.0,
                "unrealized_pnl_usd": 0.0,
                "total_pnl_usd": 0.0,
                "avg_slippage_bps": 0.0,
                "avg_notional_usd": 0.0,
                "policy_score": 0.5,
                "summary_text": "Error generating reflection"
            }
    
    def _sigmoid(self, x: float) -> float:
        """Sigmoid function for policy scoring."""
        return 1 / (1 + math.exp(-x))
    
    def _persist_reflection(self, reflection: Dict[str, Any]):
        """Persist reflection to daily log file."""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(reflection) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist reflection: {e}")
    
    def get_latest_reflection(self) -> Optional[Dict[str, Any]]:
        """Get the latest reflection summary."""
        try:
            if not os.path.exists(self.log_file):
                return None
            
            with open(self.log_file, "r") as f:
                lines = f.readlines()
                if not lines:
                    return None
                
                # Get the last line
                last_line = lines[-1].strip()
                if last_line:
                    return json.loads(last_line)
                
            return None
            
        except Exception as e:
            logger.error(f"Failed to get latest reflection: {e}")
            return None
    
    def get_reflection_stats(self) -> Dict[str, Any]:
        """Get current reflection statistics."""
        try:
            latest = self.get_latest_reflection()
            if not latest:
                return {
                    "win_rate": 0.0,
                    "pnl_10_usd": 0.0,
                    "policy_score": 0.5,
                    "updated_at": None,
                    "adaptive_clamps": 0
                }
            
            return {
                "win_rate": latest.get("win_rate", 0.0),
                "pnl_10_usd": latest.get("total_pnl_usd", 0.0),
                "policy_score": latest.get("policy_score", 0.5),
                "updated_at": latest.get("ts"),
                "adaptive_clamps": latest.get("adaptive_clamps", 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get reflection stats: {e}")
            return {
                "win_rate": 0.0,
                "pnl_10_usd": 0.0,
                "policy_score": 0.5,
                "updated_at": None,
                "adaptive_clamps": 0
            }
    
    def should_clamp_notional(self) -> bool:
        """Check if notional should be clamped based on performance."""
        try:
            latest = self.get_latest_reflection()
            if not latest:
                return False
            
            policy_score = latest.get("policy_score", 0.5)
            pnl_10 = latest.get("total_pnl_usd", 0.0)
            
            # Clamp if policy score is low or PnL is negative
            return policy_score < 0.45 or pnl_10 < 0
            
        except Exception as e:
            logger.error(f"Failed to check notional clamp: {e}")
            return False

# Global reflection system
_reflection_system = ReflectionSystem()

def check_and_generate_reflection() -> Optional[Dict[str, Any]]:
    """Check if reflection should be generated."""
    return _reflection_system.check_and_generate_reflection()

def get_latest_reflection() -> Optional[Dict[str, Any]]:
    """Get the latest reflection summary."""
    return _reflection_system.get_latest_reflection()

def get_reflection_stats() -> Dict[str, Any]:
    """Get current reflection statistics."""
    return _reflection_system.get_reflection_stats()

def should_clamp_notional() -> bool:
    """Check if notional should be clamped based on performance."""
    return _reflection_system.should_clamp_notional()
