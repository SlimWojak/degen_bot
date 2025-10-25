"""
Order Bus - Idempotency cache and audit logging for order management.
Handles order deduplication, audit trails, and order lifecycle tracking.
"""

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from backend.schemas.order_intent import OrderIntent, OrderValidationResult

logger = logging.getLogger("order_bus")

@dataclass
class EnqueuedResult:
    """Result of order submission to bus."""
    success: bool
    order_id: Optional[str] = None
    idempotent: bool = False
    validation_result: Optional[OrderValidationResult] = None
    error_message: Optional[str] = None
    timestamp: str = ""

class IdempotencyCache:
    """LRU cache for order idempotency with time-based expiration."""
    
    def __init__(self, window_seconds: int = 60, max_size: int = 1000):
        self.window_seconds = window_seconds
        self.max_size = max_size
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
    
    async def check_and_store(self, intent_id: str, order_data: Dict[str, Any]) -> bool:
        """
        Check if intent_id exists and store if not.
        
        Args:
            intent_id: Unique intent identifier
            order_data: Order data to store
            
        Returns:
            True if idempotent (already exists), False if new
        """
        async with self._lock:
            # Clean expired entries
            await self._clean_expired()
            
            # Check if exists
            if intent_id in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(intent_id)
                logger.info(f"[idempotency] Intent {intent_id} is idempotent")
                return True
            
            # Store new entry
            self.cache[intent_id] = {
                "order_data": order_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "created_at": time.time()
            }
            
            # Enforce max size
            if len(self.cache) > self.max_size:
                self.cache.popitem(last=False)
            
            logger.info(f"[idempotency] Stored new intent {intent_id}")
            return False
    
    async def get(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Get order data by intent_id."""
        async with self._lock:
            if intent_id in self.cache:
                self.cache.move_to_end(intent_id)
                return self.cache[intent_id]
            return None
    
    async def _clean_expired(self):
        """Remove expired entries from cache."""
        now = time.time()
        expired_keys = []
        
        for intent_id, data in self.cache.items():
            if now - data["created_at"] > self.window_seconds:
                expired_keys.append(intent_id)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.debug(f"[idempotency] Cleaned {len(expired_keys)} expired entries")

class OrderBus:
    """Order bus for managing order lifecycle with idempotency and audit."""
    
    def __init__(self):
        self.idempotency_cache = IdempotencyCache(window_seconds=60)
        self.audit_log_path = f"logs/orders/{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        
        # Ensure audit log directory exists
        os.makedirs(os.path.dirname(self.audit_log_path), exist_ok=True)
    
    async def submit(self, order_intent: OrderIntent, current_positions: Dict[str, float] = None) -> EnqueuedResult:
        """
        Submit order intent to the bus with validation and idempotency checks.
        
        Args:
            order_intent: Order intent to submit
            current_positions: Current positions for risk calculation
            
        Returns:
            EnqueuedResult with submission status
        """
        try:
            # Check idempotency
            order_data = order_intent.dict()
            is_idempotent = await self.idempotency_cache.check_and_store(
                order_intent.intent_id, 
                order_data
            )
            
            if is_idempotent:
                return EnqueuedResult(
                    success=False,
                    idempotent=True,
                    error_message="Order intent already processed",
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
            
            # Validate order
            from backend.schemas.order_intent import validate_order_intent, clip_to_risk
            validation_result = validate_order_intent(order_intent, current_positions)
            
            if not validation_result.valid:
                await self._log_audit_event({
                    "event": "order_rejected",
                    "intent_id": order_intent.intent_id,
                    "reason": "validation_failed",
                    "errors": validation_result.errors,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                return EnqueuedResult(
                    success=False,
                    validation_result=validation_result,
                    error_message="; ".join(validation_result.errors),
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
            
            # Clip to risk if needed
            if validation_result.risk_adjusted:
                order_intent = clip_to_risk(order_intent, current_positions)
                logger.info(f"[order_bus] Order clipped to risk limits: {order_intent.size}")
            
            # Generate order ID
            order_id = f"ord_{order_intent.intent_id}_{int(time.time())}"
            
            # Store in pending orders
            self.pending_orders[order_id] = {
                "intent_id": order_intent.intent_id,
                "order_intent": order_intent.dict(),
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Log audit event
            await self._log_audit_event({
                "event": "order_submitted",
                "order_id": order_id,
                "intent_id": order_intent.intent_id,
                "symbol": order_intent.symbol,
                "side": order_intent.side,
                "size": order_intent.size,
                "type": order_intent.type,
                "validation_warnings": validation_result.warnings,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"[order_bus] Order {order_id} submitted successfully")
            
            return EnqueuedResult(
                success=True,
                order_id=order_id,
                validation_result=validation_result,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"[order_bus] Failed to submit order: {e}")
            
            await self._log_audit_event({
                "event": "order_error",
                "intent_id": order_intent.intent_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return EnqueuedResult(
                success=False,
                error_message=str(e),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
    
    async def update_order_status(self, order_id: str, status: str, details: Dict[str, Any] = None):
        """Update order status and log audit event."""
        try:
            if order_id in self.pending_orders:
                self.pending_orders[order_id]["status"] = status
                if details:
                    self.pending_orders[order_id].update(details)
            
            await self._log_audit_event({
                "event": "order_status_update",
                "order_id": order_id,
                "status": status,
                "details": details or {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"[order_bus] Order {order_id} status updated to {status}")
            
        except Exception as e:
            logger.error(f"[order_bus] Failed to update order status: {e}")
    
    async def _log_audit_event(self, event_data: Dict[str, Any]):
        """Log audit event to append-only JSONL file."""
        try:
            with open(self.audit_log_path, "a") as f:
                f.write(json.dumps(event_data) + "\n")
        except Exception as e:
            logger.error(f"[order_bus] Failed to log audit event: {e}")
    
    def get_pending_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent pending orders."""
        orders = list(self.pending_orders.values())
        return orders[-limit:] if orders else []
    
    def get_audit_tail(self, lines: int = 50) -> List[Dict[str, Any]]:
        """Get last N lines from audit log."""
        try:
            if not os.path.exists(self.audit_log_path):
                return []
            
            with open(self.audit_log_path, "r") as f:
                all_lines = f.readlines()
                tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                
                return [json.loads(line.strip()) for line in tail_lines if line.strip()]
                
        except Exception as e:
            logger.error(f"[order_bus] Failed to read audit log: {e}")
            return []
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order by ID."""
        return self.pending_orders.get(order_id)
    
    def get_order_by_intent_id(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """Get order by intent ID."""
        for order in self.pending_orders.values():
            if order.get("intent_id") == intent_id:
                return order
        return None

# Global order bus instance
order_bus = OrderBus()
