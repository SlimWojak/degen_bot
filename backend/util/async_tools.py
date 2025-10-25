"""
Async Hygiene Tools - Phase ε.1 Purification Pass
Provides supervised task management, timeouts, and retry logic for deterministic async operations.
"""

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar
from functools import wraps

logger = logging.getLogger(__name__)

# Global registry for supervised tasks
_supervised_tasks: Dict[str, asyncio.Task] = {}
_shutdown_event = asyncio.Event()

T = TypeVar('T')

class AsyncTimeoutError(Exception):
    """Raised when an async operation times out."""
    pass

class AsyncRetryError(Exception):
    """Raised when an async operation fails after all retries."""
    pass

def create_supervised_task(
    coro: Awaitable[T], 
    *, 
    name: str, 
    shield: bool = False
) -> asyncio.Task[T]:
    """
    Create a supervised task that will be cancelled on shutdown.
    
    Args:
        coro: The coroutine to run
        name: Unique name for the task (used for tracking)
        shield: If True, task won't be cancelled during shutdown
        
    Returns:
        The created task
        
    Raises:
        ValueError: If a task with the same name already exists
    """
    if name in _supervised_tasks:
        raise ValueError(f"Task '{name}' already exists")
    
    async def _supervised_wrapper():
        try:
            return await coro
        except asyncio.CancelledError:
            logger.info(f"[async_tools] Task '{name}' cancelled")
            raise
        except Exception as e:
            logger.error(f"[async_tools] Task '{name}' failed: {e}")
            raise
    
    task = asyncio.create_task(_supervised_wrapper(), name=name)
    _supervised_tasks[name] = task
    
    if shield:
        # Shield from cancellation during shutdown
        task = asyncio.shield(task)
    
    return task

async def timeout(awaitable: Awaitable[T], seconds: float) -> T:
    """
    Add a timeout to an awaitable.
    
    Args:
        awaitable: The coroutine to timeout
        seconds: Timeout in seconds
        
    Returns:
        The result of the awaitable
        
    Raises:
        AsyncTimeoutError: If the operation times out
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except asyncio.TimeoutError:
        raise AsyncTimeoutError(f"Operation timed out after {seconds}s")

async def retry_async(
    func: Callable[[], Awaitable[T]], 
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> T:
    """
    Retry an async function with exponential backoff and jitter.
    
    Args:
        func: The async function to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for delay after each failure
        jitter: Whether to add random jitter to delays
        
    Returns:
        The result of the function
        
    Raises:
        AsyncRetryError: If all attempts fail
    """
    last_exception = None
    delay = base_delay
    
    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt == max_attempts - 1:
                break
                
            # Calculate delay with jitter
            actual_delay = min(delay, max_delay)
            if jitter:
                # Add ±25% jitter
                jitter_factor = random.uniform(0.75, 1.25)
                actual_delay *= jitter_factor
            
            logger.warning(f"[async_tools] Attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {actual_delay:.2f}s")
            await asyncio.sleep(actual_delay)
            delay *= backoff_factor
    
    raise AsyncRetryError(f"Function failed after {max_attempts} attempts") from last_exception

async def shutdown_supervised_tasks():
    """Cancel all supervised tasks and wait for them to complete."""
    if not _supervised_tasks:
        return
    
    logger.info(f"[async_tools] Shutting down {len(_supervised_tasks)} supervised tasks")
    
    # Cancel all tasks
    for name, task in _supervised_tasks.items():
        if not task.done():
            task.cancel()
    
    # Wait for all tasks to complete
    if _supervised_tasks:
        await asyncio.gather(*_supervised_tasks.values(), return_exceptions=True)
    
    _supervised_tasks.clear()
    logger.info("[async_tools] All supervised tasks shut down")

def get_supervised_tasks() -> Dict[str, asyncio.Task]:
    """Get the current supervised tasks registry."""
    return _supervised_tasks.copy()

def seeded_random(seed: int = 1337):
    """Decorator to seed random number generators for deterministic tests."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Seed Python's random module
            random.seed(seed)
            
            # Seed numpy if available
            try:
                import numpy as np
                np.random.seed(seed)
            except ImportError:
                pass
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class DeterministicClock:
    """A deterministic clock for testing that can be frozen and advanced."""
    
    def __init__(self, start_time: float = 0.0):
        self._time = start_time
        self._frozen = False
    
    def time(self) -> float:
        """Get current time."""
        if self._frozen:
            return self._time
        return time.time()
    
    def freeze(self):
        """Freeze the clock at current time."""
        self._frozen = True
        self._time = time.time()
    
    def advance(self, seconds: float):
        """Advance the clock by the given number of seconds."""
        if not self._frozen:
            raise RuntimeError("Clock must be frozen to advance")
        self._time += seconds
    
    def unfreeze(self):
        """Unfreeze the clock to use real time."""
        self._frozen = False

# Global deterministic clock for tests
_deterministic_clock = DeterministicClock()

def get_deterministic_clock() -> DeterministicClock:
    """Get the global deterministic clock."""
    return _deterministic_clock

def time_deterministic() -> float:
    """Get deterministic time for testing."""
    return _deterministic_clock.time()
