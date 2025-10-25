"""
Ring buffer implementation for market data.
Small, dependency-free ring buffer wrapper.
"""

from typing import TypeVar, List, Generic
import time

T = TypeVar('T')

class RingBuffer(Generic[T]):
    """Thread-safe ring buffer with fixed capacity."""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer: List[T] = []
        self.head = 0
        self.size = 0
    
    def append(self, item: T) -> None:
        """Add item to buffer, overwriting oldest if full."""
        if self.size < self.capacity:
            self.buffer.append(item)
            self.size += 1
        else:
            self.buffer[self.head] = item
            self.head = (self.head + 1) % self.capacity
    
    def to_list(self) -> List[T]:
        """Get all items in chronological order (oldest first)."""
        if self.size == 0:
            return []
        
        if self.size < self.capacity:
            return self.buffer.copy()
        
        # Buffer is full, need to reorder
        result = []
        for i in range(self.capacity):
            idx = (self.head + i) % self.capacity
            result.append(self.buffer[idx])
        return result
    
    def to_list_recent(self) -> List[T]:
        """Get all items in reverse chronological order (newest first)."""
        items = self.to_list()
        return list(reversed(items))
    
    def get_latest(self) -> T:
        """Get the most recent item."""
        if self.size == 0:
            raise IndexError("Buffer is empty")
        
        if self.size < self.capacity:
            return self.buffer[-1]
        
        # Buffer is full, get item at head-1 position
        idx = (self.head - 1) % self.capacity
        return self.buffer[idx]
    
    def get_latest_n(self, n: int) -> List[T]:
        """Get the n most recent items (newest first)."""
        items = self.to_list_recent()
        return items[:n]
    
    def clear(self) -> None:
        """Clear the buffer."""
        self.buffer.clear()
        self.head = 0
        self.size = 0
    
    def __len__(self) -> int:
        return self.size
    
    def __bool__(self) -> bool:
        return self.size > 0
