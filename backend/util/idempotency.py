"""
Idempotency headers for order deduplication.
Tracks X-Intent-ID headers with 60s dedupe window.
"""

import time
import uuid
import logging
from typing import Dict, Set
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class IntentRecord:
    """Record of an intent ID with timestamp."""
    intent_id: str
    timestamp: float
    endpoint: str

class IdempotencyTracker:
    """Tracks intent IDs for deduplication."""
    
    def __init__(self, window_seconds: int = 60, max_records: int = 50):
        self.window_seconds = window_seconds
        self.max_records = max_records
        self.records = deque()  # (timestamp, intent_id, endpoint)
        self.active_intents: Set[str] = set()
    
    def is_duplicate(self, intent_id: str, endpoint: str = "order") -> bool:
        """Check if intent ID is a duplicate within the window."""
        now = time.time()
        
        # Clean old records
        while self.records and self.records[0].timestamp < now - self.window_seconds:
            old_record = self.records.popleft()
            self.active_intents.discard(old_record.intent_id)
        
        # Check if intent ID already exists
        if intent_id in self.active_intents:
            logger.warning(f"Duplicate intent ID detected: {intent_id} for {endpoint}")
            return True
        
        return False
    
    def record_intent(self, intent_id: str, endpoint: str = "order"):
        """Record a new intent ID."""
        now = time.time()
        
        # Add to records
        record = IntentRecord(intent_id, now, endpoint)
        self.records.append(record)
        self.active_intents.add(intent_id)
        
        # Trim if too many records
        while len(self.records) > self.max_records:
            old_record = self.records.popleft()
            self.active_intents.discard(old_record.intent_id)
        
        logger.debug(f"Recorded intent ID: {intent_id} for {endpoint}")
    
    def get_stats(self) -> Dict:
        """Get idempotency tracker statistics."""
        now = time.time()
        active_count = len(self.active_intents)
        total_records = len(self.records)
        
        return {
            "active_intents": active_count,
            "total_records": total_records,
            "window_seconds": self.window_seconds,
            "max_records": self.max_records
        }

# Global tracker instance
_tracker = IdempotencyTracker()

def generate_intent_id() -> str:
    """Generate a new intent ID."""
    return str(uuid.uuid4())

def check_duplicate(intent_id: str, endpoint: str = "order") -> bool:
    """Check if intent ID is a duplicate."""
    return _tracker.is_duplicate(intent_id, endpoint)

def record_intent(intent_id: str, endpoint: str = "order"):
    """Record a new intent ID."""
    _tracker.record_intent(intent_id, endpoint)

def get_stats() -> Dict:
    """Get idempotency tracker statistics."""
    return _tracker.get_stats()

def reset():
    """Reset tracker (for testing)."""
    global _tracker
    _tracker = IdempotencyTracker()
