"""
Operations monitoring endpoints.
Provides lightweight monitoring for frontend and health monitors.
"""

import time
import logging
from fastapi import APIRouter
from backend.util.breakers import get_all_status
from backend.util.idempotency import get_stats as get_idempotency_stats
from backend.util.budget_guard import get_status as get_budget_status
from backend.observability.metrics import get_info_limiter_stats, get_order_limiter_stats
from backend.exchange.order_bus import order_bus

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/ops/cockpit")
def get_cockpit():
    """Lightweight monitoring endpoint for frontend and health monitors."""
    try:
        # Get WebSocket state
        ws_connected = False
        last_msg_ms_ago = None
        
        # Try to get WebSocket state from app state
        try:
            from fastapi import Request
            # This is a simplified check - in real implementation, 
            # you'd get this from the actual WebSocket service
            ws_connected = True  # Placeholder
            last_msg_ms_ago = 120  # Placeholder
        except Exception:
            pass
        
        # Get rate limiter stats
        info_stats = get_info_limiter_stats()
        order_stats = get_order_limiter_stats()
        
        # Get circuit breaker status
        breaker_status = get_all_status()
        breaker_active = any(status.get("tripped", False) for status in breaker_status.values())
        
        # Get budget guard status
        budget_status = get_budget_status()
        
        # Get idempotency stats
        idempotency_stats = get_idempotency_stats()
        
        # Get simulation metrics
        from backend.services.sim_broker import get_sim_broker
        sim_broker = get_sim_broker()
        sim_metrics = sim_broker.get_metrics()
        
        # Get live guard status
        from backend.util.live_guard import get_live_guard_status
        live_guard_status = get_live_guard_status()
        
        return {
            "ws_connected": ws_connected,
            "last_msg_ms_ago": last_msg_ms_ago,
            "info_limiter_tokens": info_stats.tokens,
            "order_limiter_tokens": order_stats.tokens,
            "breaker_active": breaker_active,
            "budget_pct": budget_status.get("drawdown_pct", 0.0),
            "budget_triggered": budget_status.get("triggered", False),
            "active_intents": idempotency_stats.get("active_intents", 0),
            "live_guard": live_guard_status,
            "sim": {
                "trades": sim_metrics["trades"],
                "win_rate": sim_metrics["win_rate"],
                "pnl_usd": sim_metrics["realized_pnl_usd"] + sim_metrics["unrealized_pnl_usd"]
            },
            "timestamp": int(time.time() * 1000)
        }
        
    except Exception as e:
        logger.error(f"Error in cockpit endpoint: {e}")
        return {
            "error": str(e),
            "timestamp": int(time.time() * 1000)
        }

@router.get("/ops/breakers")
def get_breakers():
    """Get circuit breaker status."""
    return get_all_status()

@router.get("/ops/budget")
def get_budget():
    """Get budget guard status."""
    return get_budget_status()

@router.get("/ops/idempotency")
def get_idempotency():
    """Get idempotency tracker status."""
    return get_idempotency_stats()

@router.get("/ops/data-health")
def get_data_health():
    """Get market data health metrics."""
    try:
        from backend.services.market_sampler import get_sampler
        
        sampler = get_sampler()
        if not sampler:
            return {
                "error": "Market sampler not available",
                "status": "error"
            }
        
        health_metrics = sampler.get_health_metrics()
        return health_metrics
        
    except Exception as e:
        logger.error(f"Error getting data health: {e}")
        return {
            "error": str(e),
            "status": "error"
        }

@router.get("/ops/ai-health")
def get_ai_health():
    """Get AI health metrics."""
    try:
        from backend.observability.ai_health import get_ai_health_metrics
        
        metrics = get_ai_health_metrics()
        return metrics
        
    except Exception as e:
        logger.error(f"Error getting AI health: {e}")
        return {
            "error": str(e),
            "status": "error"
        }

@router.get("/ops/orders/pending")
def get_pending_orders(limit: int = 20):
    """Get recent pending orders."""
    try:
        orders = order_bus.get_pending_orders(limit=limit)
        return {
            "orders": orders,
            "count": len(orders),
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error getting pending orders: {e}")
        return {
            "error": str(e),
            "orders": [],
            "count": 0
        }

@router.get("/ops/orders/audit")
def get_order_audit(lines: int = 50):
    """Get order audit trail."""
    try:
        audit_events = order_bus.get_audit_tail(lines=lines)
        return {
            "events": audit_events,
            "count": len(audit_events),
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error getting order audit: {e}")
        return {
            "error": str(e),
            "events": [],
            "count": 0
        }
