"""
Observability metrics for monitoring and debugging.
Provides rate limiting, WebSocket, and system health metrics.
"""

from fastapi import APIRouter, Response
from typing import Dict, List, Optional, Any
import time
import json

# Simple metrics tracking without Prometheus dependency
class SimpleMetrics:
    """Simple metrics tracking for observability."""
    
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = {}
    
    def inc_counter(self, name: str, labels: Dict[str, str] = None):
        """Increment a counter."""
        key = f"{name}_{json.dumps(labels or {}, sort_keys=True)}"
        self.counters[key] = self.counters.get(key, 0) + 1
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge value."""
        key = f"{name}_{json.dumps(labels or {}, sort_keys=True)}"
        self.gauges[key] = value
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a histogram value."""
        key = f"{name}_{json.dumps(labels or {}, sort_keys=True)}"
        if key not in self.histograms:
            self.histograms[key] = []
        self.histograms[key].append(value)
        # Keep only last 1000 samples
        if len(self.histograms[key]) > 1000:
            self.histograms[key] = self.histograms[key][-1000:]
    
    def get_metrics(self) -> str:
        """Get metrics in text format."""
        lines = []
        for key, value in self.counters.items():
            lines.append(f"# TYPE {key.split('_')[0]} counter")
            lines.append(f"{key} {value}")
        for key, value in self.gauges.items():
            lines.append(f"# TYPE {key.split('_')[0]} gauge")
            lines.append(f"{key} {value}")
        for key, values in self.histograms.items():
            if values:
                lines.append(f"# TYPE {key.split('_')[0]} histogram")
                lines.append(f"{key}_count {len(values)}")
                lines.append(f"{key}_sum {sum(values)}")
                lines.append(f"{key}_avg {sum(values)/len(values)}")
        return "\n".join(lines)

# Global metrics instance
_metrics = SimpleMetrics()

def record_rate_limit_acquire(kind: str, queued_ms: float):
    """Record rate limiter acquire event."""
    _metrics.inc_counter("ratelimit_acquired", {"kind": kind})
    _metrics.observe_histogram("ratelimit_queue_ms", queued_ms, {"kind": kind})

def record_rate_limit_tokens(kind: str, tokens: float, capacity: float):
    """Record current rate limiter state."""
    _metrics.set_gauge("ratelimit_tokens", tokens, {"kind": kind})
    _metrics.set_gauge("ratelimit_capacity", capacity, {"kind": kind})

def record_ws_reconnect():
    """Record WebSocket reconnection."""
    _metrics.inc_counter("ws_reconnects")

def record_ws_message(msg_type: str):
    """Record WebSocket message received."""
    _metrics.inc_counter("ws_messages", {"type": msg_type})

def record_ws_lag(lag_ms: float):
    """Record WebSocket message lag."""
    _metrics.set_gauge("ws_lag_ms", lag_ms)

def record_system_health(component: str, status: float):
    """Record system health status (1.0 = healthy, 0.0 = unhealthy)."""
    _metrics.set_gauge("system_health", status, {"component": component})

def record_api_request(endpoint: str, status_code: int, duration_ms: float):
    """Record API request metrics."""
    status = "success" if 200 <= status_code < 400 else "error"
    _metrics.inc_counter("api_requests", {"endpoint": endpoint, "status": status})
    _metrics.observe_histogram("api_duration_ms", duration_ms, {"endpoint": endpoint})

def record_market_snapshot(symbol: str, insufficient: bool = False, reason: str = None):
    """Record market snapshot request."""
    _metrics.inc_counter("market_snapshots", {"symbol": symbol})
    if insufficient:
        _metrics.inc_counter("market_insufficient", {"symbol": symbol, "reason": reason or "unknown"})

def get_metrics() -> str:
    """Get metrics in text format."""
    return _metrics.get_metrics()

def create_metrics_router() -> APIRouter:
    """Create FastAPI router for metrics endpoint."""
    router = APIRouter()
    
    @router.get("/ops/metrics")
    def metrics():
        """Metrics endpoint."""
        return Response(get_metrics(), media_type="text/plain")
    
    return router

# Rate limiter state tracking
class RateLimiterStats:
    """Track rate limiter statistics for Lucidity feed."""
    
    def __init__(self, kind: str):
        self.kind = kind
        self.queue_times: list = []
        self.acquired_count = 0
        self.last_refill_ms = 0
        self.rps = 0
        self.burst = 0
        self.tokens = 0
    
    def record_acquire(self, queued_ms: float):
        """Record acquire event."""
        self.acquired_count += 1
        self.queue_times.append(queued_ms)
        # Keep only last 100 samples for rolling stats
        if len(self.queue_times) > 100:
            self.queue_times = self.queue_times[-100:]
    
    def get_queue_p50(self) -> float:
        """Get 50th percentile queue time."""
        if not self.queue_times:
            return 0.0
        sorted_times = sorted(self.queue_times)
        idx = int(len(sorted_times) * 0.5)
        return sorted_times[idx]
    
    def get_queue_p95(self) -> float:
        """Get 95th percentile queue time."""
        if not self.queue_times:
            return 0.0
        sorted_times = sorted(self.queue_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Lucidity feed."""
        return {
            "rps": self.rps,
            "burst": self.burst,
            "tokens": self.tokens,
            "acquired_total": self.acquired_count,
            "queued_ms_p50": self.get_queue_p50(),
            "queued_ms_p95": self.get_queue_p95()
        }

# Global rate limiter stats
_info_limiter_stats = RateLimiterStats("info")
_order_limiter_stats = RateLimiterStats("order")

def get_info_limiter_stats() -> RateLimiterStats:
    """Get info rate limiter statistics."""
    return _info_limiter_stats

def get_order_limiter_stats() -> RateLimiterStats:
    """Get order rate limiter statistics."""
    return _order_limiter_stats