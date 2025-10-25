"""
Async token bucket rate limiter for Hyperliquid API calls.
Provides smooth rate limiting with burst capacity and refill rate.
"""

import asyncio
import time
import logging
from typing import Optional
from dataclasses import dataclass

# Import metrics for recording
try:
    from backend.observability.metrics import (
        record_rate_limit_acquire, record_rate_limit_tokens,
        get_info_limiter_stats, get_order_limiter_stats
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class RateLimitStats:
    """Rate limiter statistics for monitoring."""
    tokens_available: float
    tokens_consumed: int
    wait_time_ms: float
    last_refill: float

class TokenBucket:
    """
    Async token bucket rate limiter.
    
    Features:
    - Smooth rate limiting with burst capacity
    - Returns within ≤250ms if possible, otherwise waits for next refill
    - Thread-safe async operations
    - Statistics tracking for monitoring
    """
    
    def __init__(self, rps: float, burst: int, name: str = "limiter"):
        """
        Initialize token bucket.
        
        Args:
            rps: Tokens per second (refill rate)
            burst: Maximum burst capacity
            name: Name for logging
        """
        self.rps = rps
        self.burst = burst
        self.name = name
        
        # Token bucket state
        self.tokens = float(burst)  # Current tokens available
        self.last_refill = time.time()
        
        # Statistics
        self.tokens_consumed = 0
        self.total_wait_time = 0.0
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info(f"Initialized {name}: rps={rps}, burst={burst}")
    
    async def acquire(self, tokens: int = 1, timeout_ms: int = 200) -> bool:
        """
        Acquire tokens from the bucket with timeout.
        
        Args:
            tokens: Number of tokens to acquire (default: 1)
            timeout_ms: Maximum wait time in milliseconds (default: 200)
            
        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.time()
        timeout_seconds = timeout_ms / 1000.0
        
        async with self._lock:
            # Refill tokens based on elapsed time
            now = time.time()
            elapsed = now - self.last_refill
            refill_amount = elapsed * self.rps
            
            if refill_amount > 0:
                self.tokens = min(self.burst, self.tokens + refill_amount)
                self.last_refill = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                # We have tokens, consume them
                self.tokens -= tokens
                self.tokens_consumed += tokens
                
                wait_time = (time.time() - start_time) * 1000
                self.total_wait_time += wait_time
                
                # Record metrics
                if METRICS_AVAILABLE:
                    record_rate_limit_acquire(self.name, wait_time)
                    record_rate_limit_tokens(self.name, self.tokens, self.burst)
                    
                    # Update stats for Lucidity feed
                    try:
                        from backend.observability.metrics import get_info_limiter_stats, get_order_limiter_stats
                        if self.name == "info":
                            stats = get_info_limiter_stats()
                            stats.record_acquire(wait_time)
                            stats.rps = self.rps
                            stats.burst = self.burst
                            stats.tokens = self.tokens
                        elif self.name == "order":
                            stats = get_order_limiter_stats()
                            stats.record_acquire(wait_time)
                            stats.rps = self.rps
                            stats.burst = self.burst
                            stats.tokens = self.tokens
                    except ImportError:
                        pass
                
                logger.debug(f"{self.name}: acquired {tokens} tokens, wait={wait_time:.1f}ms")
                return True
            
            # Not enough tokens, check if we can wait within timeout
            tokens_needed = tokens - self.tokens
            wait_seconds = tokens_needed / self.rps
            
            # If wait time is within timeout, wait
            if wait_seconds <= timeout_seconds:
                await asyncio.sleep(wait_seconds)
                
                # Refill after wait
                self.tokens = min(self.burst, self.tokens + wait_seconds * self.rps)
                self.tokens -= tokens
                self.tokens_consumed += tokens
                
                wait_time = (time.time() - start_time) * 1000
                self.total_wait_time += wait_time
                
                # Record metrics
                if METRICS_AVAILABLE:
                    record_rate_limit_acquire(self.name, wait_time)
                    record_rate_limit_tokens(self.name, self.tokens, self.burst)
                
                logger.debug(f"{self.name}: waited {wait_seconds:.3f}s for {tokens} tokens, total={wait_time:.1f}ms")
                return True
            
            # Timeout would be exceeded, return False
            waited_ms = (time.time() - start_time) * 1000
            queued_ms = min(waited_ms, timeout_ms)
            
            # Record metrics for timeout
            if METRICS_AVAILABLE:
                record_rate_limit_acquire(self.name, queued_ms)
            
            logger.warning(f"{self.name}: timeout after {waited_ms:.1f}ms, tokens={self.tokens:.1f}/{self.burst}")
            return False
    
    def get_stats(self) -> RateLimitStats:
        """Get current rate limiter statistics."""
        return RateLimitStats(
            tokens_available=self.tokens,
            tokens_consumed=self.tokens_consumed,
            wait_time_ms=self.total_wait_time,
            last_refill=self.last_refill
        )
    
    def reset_stats(self):
        """Reset statistics counters."""
        self.tokens_consumed = 0
        self.total_wait_time = 0.0

# Global rate limiters (singletons)
INFO_LIMITER: Optional[TokenBucket] = None
ORDER_LIMITER: Optional[TokenBucket] = None

def initialize_limiters(info_rps: float, order_rps: float, burst: int):
    """
    Initialize global rate limiters.
    
    Args:
        info_rps: Info API rate limit (requests per second)
        order_rps: Order API rate limit (requests per second)
        burst: Burst capacity for both limiters
    """
    global INFO_LIMITER, ORDER_LIMITER
    
    INFO_LIMITER = TokenBucket(info_rps, burst, "info_limiter")
    ORDER_LIMITER = TokenBucket(order_rps, burst, "order_limiter")
    
    logger.info(f"Initialized rate limiters: info_rps={info_rps}, order_rps={order_rps}, burst={burst}")

def get_info_limiter() -> TokenBucket:
    """Get the info API rate limiter."""
    if INFO_LIMITER is None:
        raise RuntimeError("Rate limiters not initialized. Call initialize_limiters() first.")
    return INFO_LIMITER

def get_order_limiter() -> TokenBucket:
    """Get the order API rate limiter."""
    if ORDER_LIMITER is None:
        raise RuntimeError("Rate limiters not initialized. Call initialize_limiters() first.")
    return ORDER_LIMITER

async def log_limiter_stats():
    """Log rate limiter statistics periodically."""
    if INFO_LIMITER and ORDER_LIMITER:
        info_stats = INFO_LIMITER.get_stats()
        order_stats = ORDER_LIMITER.get_stats()
        
        logger.info(f"Rate limiter stats: "
                   f"info_tokens={info_stats.tokens_available:.1f}, "
                   f"info_consumed={info_stats.tokens_consumed}, "
                   f"order_tokens={order_stats.tokens_available:.1f}, "
                   f"order_consumed={order_stats.tokens_consumed}")
