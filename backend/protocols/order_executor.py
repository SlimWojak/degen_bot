"""
Order Executor Protocol - Phase ε.1 Purification Pass
Defines the interface for order execution to decouple order bus.
"""

from typing import Protocol, Dict, Any, Optional
from abc import abstractmethod


class OrderExecutor(Protocol):
    """Protocol for order execution."""
    
    @abstractmethod
    async def submit(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit an order for execution."""
        ...
    
    @abstractmethod
    async def amend(self, order_id: str, amendments: Dict[str, Any]) -> Dict[str, Any]:
        """Amend an existing order."""
        ...
    
    @abstractmethod
    async def cancel(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        ...
