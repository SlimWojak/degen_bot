"""
Live guard logic for safe execution mode switching.
Checks data health, circuit breakers, and budget guard before allowing live trades.
"""

import logging
from typing import Dict, Any, Tuple
from backend.config import settings
from backend.services.market_sampler import get_sampler
from backend.util.breakers import get_all_status
from backend.util.budget_guard import get_status as get_budget_status

logger = logging.getLogger(__name__)

def check_live_guard() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Check if live execution is safe.
    
    Returns:
        Tuple of (is_safe, reason, guard_info)
    """
    try:
        # Check data health
        sampler = get_sampler()
        if not sampler:
            return False, "no_sampler", {"data_health": "unavailable"}
        
        health_metrics = sampler.get_health_metrics()
        data_health_status = health_metrics.get("status", "unknown")
        
        if data_health_status != "healthy":
            return False, "data_degraded", {
                "data_health": data_health_status,
                "notes": health_metrics.get("notes", [])
            }
        
        # Check circuit breakers
        breaker_status = get_all_status()
        breaker_active = any(status.get("tripped", False) for status in breaker_status.values())
        
        if breaker_active:
            return False, "breaker_active", {
                "breakers": breaker_status,
                "active_breakers": [name for name, status in breaker_status.items() 
                                  if status.get("tripped", False)]
            }
        
        # Check budget guard
        budget_status = get_budget_status()
        budget_triggered = budget_status.get("triggered", False)
        
        if budget_triggered:
            return False, "budget_triggered", {
                "budget_status": budget_status,
                "drawdown_pct": budget_status.get("drawdown_pct", 0.0)
            }
        
        # All checks passed
        return True, "all_green", {
            "data_health": data_health_status,
            "breakers": "ok",
            "budget": "ok"
        }
        
    except Exception as e:
        logger.error(f"Error checking live guard: {e}")
        return False, "error", {"error": str(e)}

def get_live_guard_status() -> Dict[str, Any]:
    """Get live guard status for cockpit."""
    if not settings.LIVE_GUARD:
        return {
            "active": False,
            "mode": "live",
            "reason": "guard_disabled"
        }
    
    is_safe, reason, guard_info = check_live_guard()
    
    return {
        "active": True,
        "mode": "live" if is_safe else "sim",
        "reason": reason,
        "details": guard_info
    }
