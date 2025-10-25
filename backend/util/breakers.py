"""
Circuit breakers for API failure protection.
Implements sliding window breakers that halt API calls on repeated errors.
"""

import time
import logging
from typing import Dict, List
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)

@dataclass
class BreakerConfig:
    """Circuit breaker configuration."""
    failure_window_sec: int = 30
    failure_threshold: int = 5
    reset_after_sec: int = 60

class CircuitBreaker:
    """Sliding window circuit breaker for API paths."""
    
    def __init__(self, path: str, config: BreakerConfig):
        self.path = path
        self.config = config
        self.failures = deque()  # Timestamps of failures
        self.tripped_at = None
        self.last_reset = time.time()
    
    def record_success(self):
        """Record a successful call."""
        self.failures.clear()
        if self.tripped_at:
            logger.info(f"Breaker {self.path}: reset after success")
            self.tripped_at = None
    
    def record_failure(self):
        """Record a failed call."""
        now = time.time()
        self.failures.append(now)
        
        # Clean old failures outside window
        cutoff = now - self.config.failure_window_sec
        while self.failures and self.failures[0] < cutoff:
            self.failures.popleft()
        
        # Check if we should trip
        if len(self.failures) >= self.config.failure_threshold:
            if not self.tripped_at:
                self.tripped_at = now
                logger.warning(f"Breaker {self.path}: TRIPPED after {len(self.failures)} failures")
    
    def is_tripped(self) -> bool:
        """Check if breaker is currently tripped."""
        if not self.tripped_at:
            return False
        
        # Check if enough time has passed to reset
        if time.time() - self.tripped_at > self.config.reset_after_sec:
            logger.info(f"Breaker {self.path}: auto-reset after {self.config.reset_after_sec}s")
            self.tripped_at = None
            return False
        
        return True
    
    def should_skip(self) -> bool:
        """Check if we should skip the call due to breaker."""
        return self.is_tripped()
    
    def get_status(self) -> Dict:
        """Get breaker status for monitoring."""
        return {
            "path": self.path,
            "tripped": self.is_tripped(),
            "failure_count": len(self.failures),
            "last_failure": self.failures[-1] if self.failures else None,
            "tripped_at": self.tripped_at
        }

# Global breaker instances
_breakers: Dict[str, CircuitBreaker] = {}

def get_breaker(path: str) -> CircuitBreaker:
    """Get or create breaker for a path."""
    if path not in _breakers:
        config = BreakerConfig()
        _breakers[path] = CircuitBreaker(path, config)
    return _breakers[path]

def record_success(path: str):
    """Record successful call for path."""
    get_breaker(path).record_success()

def record_failure(path: str):
    """Record failed call for path."""
    get_breaker(path).record_failure()

def should_skip(path: str) -> bool:
    """Check if we should skip call due to breaker."""
    return get_breaker(path).should_skip()

def get_all_status() -> Dict[str, Dict]:
    """Get status of all breakers."""
    return {path: breaker.get_status() for path, breaker in _breakers.items()}

def reset_all():
    """Reset all breakers (for testing)."""
    global _breakers
    _breakers.clear()
