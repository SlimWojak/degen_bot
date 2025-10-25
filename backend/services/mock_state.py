"""
Mock state service for development and testing.
Provides static data that matches the live API response shapes.
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta

class MockStateService:
    """Mock state service with static data."""
    
    @staticmethod
    def get_metrics(symbol: str = None) -> Dict[str, Any]:
        """Return mock metrics data, optionally filtered by symbol."""
        base_metrics = {
            "total_value": 10000,
            "win_rate": 0.5,
            "sharpe": 0.6,
            "max_dd": -11.1,
            "trades": 7,
            "best_pnl": 19.6,
            "worst_pnl": -10,
            "_meta": {"source": "mock"}
        }
        
        if symbol:
            # Filter metrics for specific symbol
            base_metrics["_meta"]["symbol"] = symbol
            base_metrics["_meta"]["filtered"] = True
        
        return base_metrics
    
    @staticmethod
    def get_positions(symbol: str = None) -> List[Dict[str, Any]]:
        """Return mock positions data, optionally filtered by symbol."""
        all_positions = [
            {
                "side": "long",
                "coin": "HYPE",
                "entry": 39.21,
                "current": 39.5,
                "qty": 100,
                "lev": 40,
                "sl": 38.0,
                "tp": 42.0,
                "margin": 247,
                "pnl": 18.4,
                "_meta": {"source": "mock"}
            },
            {
                "side": "short",
                "coin": "BTC",
                "entry": 111148,
                "current": 110500,
                "qty": 0.1,
                "lev": 10,
                "sl": 112000,
                "tp": 109000,
                "margin": 1111,
                "pnl": 64.8,
                "_meta": {"source": "mock"}
            }
        ]
        
        if symbol:
            # Filter positions by symbol
            filtered_positions = [pos for pos in all_positions if pos.get("coin") == symbol]
            return filtered_positions
        
        return all_positions
    
    @staticmethod
    def get_trades(limit: int = 50, symbol: str = None) -> List[Dict[str, Any]]:
        """Return mock trades data, optionally filtered by symbol."""
        all_trades = [
            {
                "side": "long",
                "coin": "HYPE",
                "entry": 39.21,
                "exit": 39.5,
                "qty": 100,
                "close_reason": "TP hit",
                "time": "10:24",
                "holding": "OH 19m",
                "notional": 3921,
                "fees": 1.5,
                "pnl": 29,
                "_meta": {"source": "mock"}
            },
            {
                "side": "short",
                "coin": "SOL",
                "entry": 192.6,
                "exit": 190.2,
                "qty": 10,
                "close_reason": "SL hit",
                "time": "09:45",
                "holding": "OH 2h 15m",
                "notional": 1926,
                "fees": 0.8,
                "pnl": -24,
                "_meta": {"source": "mock"}
            }
        ]
        
        if symbol:
            # Filter trades by symbol
            filtered_trades = [trade for trade in all_trades if trade.get("coin") == symbol]
            return filtered_trades[:limit]
        
        return all_trades[:limit]
    
    @staticmethod
    def get_equity() -> List[Dict[str, Any]]:
        """Return mock equity data."""
        # Generate some mock equity curve data
        base_time = datetime.now() - timedelta(days=30)
        equity_points = []
        
        for i in range(100):
            timestamp = base_time + timedelta(hours=i*6)
            value = 10000 + (i * 10) + (i % 7 - 3) * 50
            equity_points.append({
                "timestamp": timestamp.isoformat(),
                "value": value,
                "_meta": {"source": "mock"}
            })
        
        return equity_points
    
    @staticmethod
    def get_status() -> Dict[str, str]:
        """Return mock status data."""
        return {
            "market": "ok",
            "api": "mock",
            "db": "synced",
            "ws": "connected",
            "bot": "mock",
            "_meta": {"source": "mock"}
        }
