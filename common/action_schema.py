# common/action_schema.py
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional

Side = Literal["LONG", "SHORT"]
OrderType = Literal["LIMIT", "MARKET"]

class TradeAction(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]{2,10}$")
    side: Side
    type: OrderType
    qty: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)  # required for LIMIT
    tp: Optional[float] = Field(default=None, gt=0)
    sl: Optional[float] = Field(default=None, gt=0)
    time_in_force: Literal["GTC","FOK","IOC","POST_ONLY"] = "POST_ONLY"

    @field_validator("price")
    @classmethod
    def require_price_for_limit(cls, v, info):
        if info.data.get("type") == "LIMIT" and v is None:
            raise ValueError("price required for LIMIT")
        return v
