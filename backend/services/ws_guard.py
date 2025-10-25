"""
WebSocket Policy Violation Guard.
Handles 1008/policy violation errors with blocking and cooldown periods.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import os

logger = logging.getLogger("ws_guard")

class WSGuard:
    """Guard for WebSocket policy violations and connection management."""
    
    def __init__(self):
        self.block_until: Optional[datetime] = None
        self.block_reason: Optional[str] = None
        self.connection_id: Optional[str] = None
        self.attempts_total = 0
        self.connect_success_total = 0
        self.policy_blocks_total = 0
        self._lock = asyncio.Lock()
        
        # Configuration
        self.block_minutes = int(os.getenv("HL_WS_BLOCK_MINUTES", "60"))
        self.max_block_minutes = 120  # Cap at 2 hours
        
    def is_blocked(self) -> bool:
        """Check if WebSocket is currently blocked."""
        if self.block_until is None:
            return False
        return datetime.now(timezone.utc) < self.block_until
    
    def get_block_info(self) -> Dict[str, Any]:
        """Get current block status information."""
        if not self.is_blocked():
            return {"blocked": False}
        
        return {
            "blocked": True,
            "blocked_until": self.block_until.isoformat(),
            "reason": self.block_reason,
            "block_minutes": self.block_minutes
        }
    
    async def handle_policy_violation(self, connection_id: str) -> None:
        """Handle policy violation by setting block window."""
        async with self._lock:
            if self.block_until is not None and self.is_blocked():
                # Already blocked, extend if needed
                return
            
            self.connection_id = connection_id
            self.block_until = datetime.now(timezone.utc) + timedelta(minutes=self.block_minutes)
            self.block_reason = "policy_violation"
            self.policy_blocks_total += 1
            
            # Exponential backoff for block duration
            self.block_minutes = min(self.block_minutes * 2, self.max_block_minutes)
            
            logger.warning(
                "WS policy violation detected - blocking connections",
                extra={
                    "evt": "ws_policy_violation",
                    "block_minutes": self.block_minutes,
                    "connection_id": connection_id,
                    "blocked_until": self.block_until.isoformat()
                }
            )
    
    async def record_attempt(self) -> bool:
        """Record connection attempt and check if allowed."""
        async with self._lock:
            self.attempts_total += 1
            
            if self.is_blocked():
                logger.debug(
                    "WS connection attempt blocked",
                    extra={
                        "evt": "ws_attempt_blocked",
                        "blocked_until": self.block_until.isoformat(),
                        "reason": self.block_reason
                    }
                )
                return False
            
            return True
    
    async def record_success(self) -> None:
        """Record successful connection."""
        async with self._lock:
            self.connect_success_total += 1
            # Reset block on successful connection
            self.block_until = None
            self.block_reason = None
            self.block_minutes = int(os.getenv("HL_WS_BLOCK_MINUTES", "60"))  # Reset to default
            
            logger.info(
                "WS connection successful - block cleared",
                extra={
                    "evt": "ws_connect_success",
                    "connection_id": self.connection_id
                }
            )
    
    async def manual_unblock(self) -> None:
        """Manually clear block (dev/admin only)."""
        async with self._lock:
            self.block_until = None
            self.block_reason = None
            self.block_minutes = int(os.getenv("HL_WS_BLOCK_MINUTES", "60"))
            
            logger.info(
                "WS block manually cleared",
                extra={
                    "evt": "ws_manual_unblock",
                    "connection_id": self.connection_id
                }
            )
    
    async def force_block(self, minutes: int = 30) -> None:
        """Force block for specified minutes (safety lever)."""
        async with self._lock:
            self.block_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            self.block_reason = "manual_force_block"
            
            logger.warning(
                "WS manually blocked",
                extra={
                    "evt": "ws_manual_block",
                    "block_minutes": minutes,
                    "blocked_until": self.block_until.isoformat()
                }
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get guard statistics."""
        return {
            "attempts_total": self.attempts_total,
            "connect_success_total": self.connect_success_total,
            "policy_blocks_total": self.policy_blocks_total,
            "current_block": self.get_block_info(),
            "block_minutes": self.block_minutes
        }

# Global guard instance
ws_guard = WSGuard()
