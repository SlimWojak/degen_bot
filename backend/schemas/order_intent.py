"""
Order Intent Schema - Pydantic models for order validation and risk management.
Defines order structure, invariants, and risk clipping utilities.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, validator
from enum import Enum

logger = logging.getLogger("order_intent")

class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"

class TimeInForce(str, Enum):
    """Time in force enumeration."""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel

class OrderIntent(BaseModel):
    """Order intent with validation and risk management."""
    
    # Required fields
    symbol: str = Field(..., description="Trading symbol (e.g., BTC, ETH)")
    side: OrderSide = Field(..., description="Order side (BUY or SELL)")
    size: float = Field(..., gt=0, description="Order size (must be positive)")
    type: OrderType = Field(..., description="Order type (market or limit)")
    intent_id: str = Field(..., description="Unique intent identifier")
    
    # Optional fields
    limit_px: Optional[float] = Field(None, gt=0, description="Limit price for limit orders")
    tif: TimeInForce = Field(TimeInForce.GTC, description="Time in force")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @validator('symbol')
    def validate_symbol(cls, v):
        """Validate symbol is known."""
        known_symbols = {"BTC", "ETH", "SOL", "HYPE", "BNB"}
        if v not in known_symbols:
            raise ValueError(f"Unknown symbol: {v}. Must be one of {known_symbols}")
        return v.upper()
    
    @validator('limit_px')
    def validate_limit_price(cls, v, values):
        """Validate limit price for limit orders."""
        if values.get('type') == 'limit' and v is None:
            raise ValueError("limit_px is required for limit orders")
        if values.get('type') == 'market' and v is not None:
            raise ValueError("limit_px should not be set for market orders")
        return v
    
    @validator('size')
    def validate_size(cls, v):
        """Validate order size."""
        if v <= 0:
            raise ValueError("Order size must be positive")
        if v > 1000:  # Max position size
            raise ValueError("Order size exceeds maximum limit (1000)")
        return v
    
    class Config:
        """Pydantic configuration."""
        use_enum_values = True
        validate_assignment = True

class OrderValidationResult(BaseModel):
    """Result of order validation."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    clipped_size: Optional[float] = None
    risk_adjusted: bool = False

class RiskLimits(BaseModel):
    """Risk limits for order validation."""
    max_notional: float = 10000.0  # Max notional value
    max_leverage: float = 10.0     # Max leverage
    max_position_size: float = 1000.0  # Max position size
    min_size: float = 0.001        # Min order size
    max_size: float = 100.0        # Max order size

def validate_order_intent(order: OrderIntent, current_positions: Dict[str, float] = None) -> OrderValidationResult:
    """
    Validate order intent against business rules and risk limits.
    
    Args:
        order: Order intent to validate
        current_positions: Current positions for risk calculation
        
    Returns:
        Validation result with errors, warnings, and risk adjustments
    """
    errors = []
    warnings = []
    clipped_size = None
    risk_adjusted = False
    
    # Risk limits
    limits = RiskLimits()
    
    # Check minimum size
    if order.size < limits.min_size:
        errors.append(f"Order size {order.size} below minimum {limits.min_size}")
    
    # Check maximum size
    if order.size > limits.max_size:
        errors.append(f"Order size {order.size} exceeds maximum {limits.max_size}")
        clipped_size = limits.max_size
        risk_adjusted = True
    
    # Check notional value (mock price for now)
    mock_prices = {"BTC": 50000, "ETH": 3000, "SOL": 100, "HYPE": 0.1, "BNB": 300}
    price = mock_prices.get(order.symbol, 1000)
    notional = order.size * price
    
    if notional > limits.max_notional:
        errors.append(f"Notional value {notional:.2f} exceeds maximum {limits.max_notional}")
        clipped_size = limits.max_notional / price
        risk_adjusted = True
    
    # Check position limits
    if current_positions:
        current_pos = current_positions.get(order.symbol, 0.0)
        new_pos = current_pos + (order.size if order.side == "BUY" else -order.size)
        
        if abs(new_pos) > limits.max_position_size:
            errors.append(f"Position size {abs(new_pos):.2f} would exceed maximum {limits.max_position_size}")
            max_additional = limits.max_position_size - abs(current_pos)
            if order.side == "BUY":
                clipped_size = min(order.size, max_additional)
            else:
                clipped_size = min(order.size, max_additional)
            risk_adjusted = True
    
    # Check limit price bounds for limit orders
    if order.type == "limit" and order.limit_px:
        # Mock price bounds (in real system, would get from market data)
        price_bounds = {
            "BTC": (40000, 60000),
            "ETH": (2000, 4000),
            "SOL": (50, 150),
            "HYPE": (0.05, 0.15),
            "BNB": (200, 400)
        }
        
        bounds = price_bounds.get(order.symbol, (price * 0.8, price * 1.2))
        if not (bounds[0] <= order.limit_px <= bounds[1]):
            warnings.append(f"Limit price {order.limit_px} outside typical range {bounds}")
    
    # Check time in force
    if order.tif not in ["GTC", "IOC"]:
        errors.append(f"Invalid time in force: {order.tif}")
    
    return OrderValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        clipped_size=clipped_size,
        risk_adjusted=risk_adjusted
    )

def clip_to_risk(order: OrderIntent, current_positions: Dict[str, float] = None) -> OrderIntent:
    """
    Clip order size to risk limits.
    
    Args:
        order: Original order intent
        current_positions: Current positions for risk calculation
        
    Returns:
        Clipped order intent
    """
    validation = validate_order_intent(order, current_positions)
    
    if validation.clipped_size is not None:
        clipped_order = order.copy()
        clipped_order.size = validation.clipped_size
        logger.info(f"[order_intent] Clipped order size from {order.size} to {validation.clipped_size}")
        return clipped_order
    
    return order

def create_order_intent(
    symbol: str,
    side: str,
    size: float,
    order_type: str = "market",
    limit_px: Optional[float] = None,
    tif: str = "GTC",
    intent_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> OrderIntent:
    """
    Create order intent with validation.
    
    Args:
        symbol: Trading symbol
        side: Order side (BUY/SELL)
        size: Order size
        order_type: Order type (market/limit)
        limit_px: Limit price for limit orders
        tif: Time in force
        intent_id: Intent ID (auto-generated if None)
        meta: Additional metadata
        
    Returns:
        Validated order intent
    """
    import uuid
    
    return OrderIntent(
        symbol=symbol,
        side=side,
        size=size,
        type=order_type,
        limit_px=limit_px,
        tif=tif,
        intent_id=intent_id or str(uuid.uuid4()),
        meta=meta
    )
