"""
Structured decision logging for DeepSeek actions.
Writes to logs/decisions/YYYY-MM-DD.jsonl
"""

import json
import os
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from logging.handlers import TimedRotatingFileHandler
from backend.schemas.simulation import DecisionLog

logger = logging.getLogger(__name__)

def setup_log_rotation():
    """Setup log rotation for backend logs."""
    try:
        # Ensure log directory exists
        os.makedirs(".run", exist_ok=True)
        
        # Create rotating file handler
        handler = TimedRotatingFileHandler(
            filename=".run/backend.log",
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8"
        )
        
        # Set formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        logger.info("Log rotation configured (daily, keep 7 days)")
        
    except Exception as e:
        logger.error(f"Failed to setup log rotation: {e}")

class DecisionLogger:
    """Structured logger for DeepSeek decisions."""
    
    def __init__(self):
        self.log_dir = "logs/decisions"
        os.makedirs(self.log_dir, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y-%m-%d")
        self.log_file = os.path.join(self.log_dir, f"{self.session_id}.jsonl")
    
    def log_decision(self, 
                    symbol: str,
                    action: str,
                    notional: float,
                    reason: str,
                    intent_id: str,
                    fill_px: Optional[float] = None,
                    result: str = "pending",
                    pnl_after: Optional[float] = None,
                    latency_ms: Optional[float] = None):
        """Log a DeepSeek decision."""
        try:
            log_entry = DecisionLog(
                ts=datetime.now(timezone.utc).isoformat(),
                symbol=symbol,
                action=action,
                notional=notional,
                fill_px=fill_px,
                result=result,
                reason=reason,
                pnl_after=pnl_after,
                intent_id=intent_id,
                latency_ms=latency_ms
            )
            
            # Write to daily log file
            with open(self.log_file, "a") as f:
                f.write(log_entry.json() + "\n")
            
            logger.info(f"Decision logged: {action} {notional} {symbol} - {reason}")
            
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")
    
    def get_recent_decisions(self, limit: int = 50) -> list:
        """Get recent decisions from log file."""
        try:
            if not os.path.exists(self.log_file):
                return []
            
            decisions = []
            with open(self.log_file, "r") as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    try:
                        decision = json.loads(line.strip())
                        decisions.append(decision)
                    except json.JSONDecodeError:
                        continue
            
            return decisions
            
        except Exception as e:
            logger.error(f"Failed to read decisions: {e}")
            return []
    
    def get_evaluation_summary(self, trades_count: int = 10) -> Dict[str, Any]:
        """Generate evaluation summary for DeepSeek reflection."""
        try:
            decisions = self.get_recent_decisions(trades_count)
            if not decisions:
                return {
                    "period": f"last_{trades_count}_trades",
                    "trades": 0,
                    "wins": 0,
                    "win_rate_pct": 0.0,
                    "pnl_total_usd": 0.0,
                    "avg_slippage_bps": 0.0,
                    "summary_text": "No recent trades"
                }
            
            # Calculate metrics
            filled_trades = [d for d in decisions if d.get("result") == "filled"]
            wins = len([d for d in filled_trades if d.get("pnl_after", 0) > 0])
            total_pnl = sum(d.get("pnl_after", 0) for d in filled_trades)
            avg_slippage = 5.0  # Placeholder - would calculate from actual fills
            
            win_rate = (wins / len(filled_trades) * 100) if filled_trades else 0.0
            
            summary_text = f"Last {len(filled_trades)} trades: {wins} wins, {total_pnl:+.1f}%, avg_slip {avg_slippage:.0f} bps"
            
            return {
                "period": f"last_{trades_count}_trades",
                "trades": len(filled_trades),
                "wins": wins,
                "win_rate_pct": win_rate,
                "pnl_total_usd": total_pnl,
                "avg_slippage_bps": avg_slippage,
                "summary_text": summary_text
            }
            
        except Exception as e:
            logger.error(f"Failed to generate evaluation summary: {e}")
            return {
                "period": f"last_{trades_count}_trades",
                "trades": 0,
                "wins": 0,
                "win_rate_pct": 0.0,
                "pnl_total_usd": 0.0,
                "avg_slippage_bps": 0.0,
                "summary_text": "Error generating summary"
            }

# Global decision logger instance
_decision_logger = DecisionLogger()

def log_decision(symbol: str, action: str, notional: float, reason: str, intent_id: str, **kwargs):
    """Log a DeepSeek decision."""
    _decision_logger.log_decision(symbol, action, notional, reason, intent_id, **kwargs)

def get_recent_decisions(limit: int = 50) -> list:
    """Get recent decisions."""
    return _decision_logger.get_recent_decisions(limit)

def get_evaluation_summary(trades_count: int = 10) -> Dict[str, Any]:
    """Get evaluation summary."""
    return _decision_logger.get_evaluation_summary(trades_count)
