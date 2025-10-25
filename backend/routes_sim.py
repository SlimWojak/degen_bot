"""
Simulation routes for SimBroker.
Provides endpoints for simulated positions, trades, and metrics.
"""

import logging
from fastapi import APIRouter
from backend.services.sim_broker import get_sim_broker

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/sim/positions")
def get_sim_positions():
    """Get simulated positions."""
    try:
        sim_broker = get_sim_broker()
        positions = sim_broker.get_positions()
        return {
            "positions": positions,
            "count": len(positions),
            "timestamp": sim_broker.balance.timestamp
        }
    except Exception as e:
        logger.error(f"Error getting sim positions: {e}")
        return {"error": str(e), "positions": [], "count": 0}

@router.get("/sim/trades")
def get_sim_trades(limit: int = 50):
    """Get simulated trades."""
    try:
        sim_broker = get_sim_broker()
        trades = sim_broker.get_trades(limit)
        return {
            "trades": trades,
            "count": len(trades),
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error getting sim trades: {e}")
        return {"error": str(e), "trades": [], "count": 0}

@router.get("/sim/balance")
def get_sim_balance():
    """Get simulated balance."""
    try:
        sim_broker = get_sim_broker()
        balance = sim_broker.get_balance()
        return balance
    except Exception as e:
        logger.error(f"Error getting sim balance: {e}")
        return {"error": str(e)}

@router.get("/sim/metrics")
def get_sim_metrics():
    """Get simulation metrics."""
    try:
        sim_broker = get_sim_broker()
        metrics = sim_broker.get_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Error getting sim metrics: {e}")
        return {"error": str(e)}

@router.post("/sim/reset")
def reset_simulation():
    """Reset simulation state (for testing)."""
    try:
        sim_broker = get_sim_broker()
        sim_broker.__init__()  # Reset to initial state
        return {"message": "Simulation reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting simulation: {e}")
        return {"error": str(e)}
