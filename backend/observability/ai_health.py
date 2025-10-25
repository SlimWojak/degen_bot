"""
AI health metrics tracker for real-time monitoring.
Tracks parse success rates, AI request times, and adaptive behavior.
"""

import time
import logging
from typing import Dict, List, Any, Optional
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AIRequest:
    """Single AI request record."""
    timestamp: float
    success: bool
    request_ms: float
    reprompt: bool
    rejected: bool
    mode: str  # "sim" or "live"

class AIHealthTracker:
    """Tracks AI health metrics over time."""
    
    def __init__(self, window_sec: int = 3600):  # 1 hour window
        self.window_sec = window_sec
        self.requests: deque = deque(maxlen=1000)  # Keep last 1000 requests
        self.adaptive_clamps: int = 0
        self.recent_rejects: int = 0
        
    def record_request(self, success: bool, request_ms: float, reprompt: bool = False, 
                      rejected: bool = False, mode: str = "sim"):
        """Record an AI request."""
        request = AIRequest(
            timestamp=time.time(),
            success=success,
            request_ms=request_ms,
            reprompt=reprompt,
            rejected=rejected,
            mode=mode
        )
        self.requests.append(request)
        
        if rejected:
            self.recent_rejects += 1
    
    def record_adaptive_clamp(self):
        """Record an adaptive notional clamp."""
        self.adaptive_clamps += 1
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get current AI health metrics."""
        now = time.time()
        
        # Filter requests within window
        recent_requests = [
            req for req in self.requests 
            if now - req.timestamp <= self.window_sec
        ]
        
        if not recent_requests:
            return {
                "parse_success_1h": 1.0,
                "avg_ai_request_ms": 0.0,
                "reprompt_rate": 0.0,
                "recent_rejects": self.recent_rejects,
                "mode": "sim",
                "adaptive_clamps": self.adaptive_clamps
            }
        
        # Calculate metrics
        total_requests = len(recent_requests)
        successful_requests = sum(1 for req in recent_requests if req.success)
        reprompt_requests = sum(1 for req in recent_requests if req.reprompt)
        
        parse_success_1h = successful_requests / total_requests if total_requests > 0 else 1.0
        avg_ai_request_ms = sum(req.request_ms for req in recent_requests) / total_requests if total_requests > 0 else 0.0
        reprompt_rate = reprompt_requests / total_requests if total_requests > 0 else 0.0
        
        # Determine current mode (most recent request)
        current_mode = recent_requests[-1].mode if recent_requests else "sim"
        
        return {
            "parse_success_1h": round(parse_success_1h, 3),
            "avg_ai_request_ms": round(avg_ai_request_ms, 1),
            "reprompt_rate": round(reprompt_rate, 3),
            "recent_rejects": self.recent_rejects,
            "mode": current_mode,
            "adaptive_clamps": self.adaptive_clamps
        }
    
    def reset_recent_rejects(self):
        """Reset recent rejects counter."""
        self.recent_rejects = 0

# Global AI health tracker
_ai_health_tracker = AIHealthTracker()

def record_ai_request(success: bool, request_ms: float, reprompt: bool = False, 
                     rejected: bool = False, mode: str = "sim"):
    """Record an AI request."""
    _ai_health_tracker.record_request(success, request_ms, reprompt, rejected, mode)

def record_adaptive_clamp():
    """Record an adaptive notional clamp."""
    _ai_health_tracker.record_adaptive_clamp()

def get_ai_health_metrics() -> Dict[str, Any]:
    """Get current AI health metrics."""
    return _ai_health_tracker.get_health_metrics()

def reset_recent_rejects():
    """Reset recent rejects counter."""
    _ai_health_tracker.reset_recent_rejects()
