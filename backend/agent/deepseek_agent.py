"""
DeepSeek AI Agent for autonomous trading decisions.
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, validator
import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

class Decision(BaseModel):
    """AI decision model with strict validation."""
    action: str = Field(..., pattern="^(order|noop)$")
    symbol: str = Field(default="ETH")
    side: str = Field(default="buy", pattern="^(buy|sell)$")
    notional_usd: float = Field(default=0.0)
    reduce_only: bool = Field(default=False)
    cross_bps: float = Field(default=0.0)

    @validator("notional_usd")
    def v_notional(cls, v):
        if v < 0:
            raise ValueError("notional_usd must be >= 0")
        return v
    
    @validator("cross_bps")
    def v_cross(cls, v):
        if v < 0:
            raise ValueError("cross_bps must be >= 0")
        return v

async def call_deepseek(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call DeepSeek API with context and return parsed decision.
    
    Args:
        context: Trading context dictionary
        
    Returns:
        Parsed decision dict or {"action": "noop"} on error
    """
    if not settings.DEEPSEEK_API_BASE or not settings.DEEPSEEK_API_KEY:
        logger.warning("DeepSeek API not configured, returning noop")
        return {"action": "noop"}
    
    request_id = str(uuid.uuid4())
    
    # System prompt
    system_prompt = """You are a trading decision engine. Reply only with a single JSON object that matches this schema:

{"action":"order|noop","symbol":"ETH","side":"buy|sell","notional_usd":15,"reduce_only":false,"cross_bps":100}

Rules:
- If data is insufficient, return {"action":"noop"...} (you may fill other fields but they will be ignored).
- notional_usd must be a positive number.
- cross_bps is your allowed slippage/crossing budget in basis points (0–200).
- Never include explanations or extra keys. Output JSON only."""

    # Build user content from context
    user_content = json.dumps(context, separators=(',', ':'), sort_keys=True)
    
    # Prepare API request
    headers = {
        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.1,
        "max_tokens": 200
    }
    
    try:
        logger.info(f"DEEPSEEK_REQUEST: {{'request_id': '{request_id}', 'context_keys': {list(context.keys())}}}")
        
        async with httpx.AsyncClient(timeout=settings.DEEPSEEK_TIMEOUT_MS/1000) as client:
            response = await client.post(
                f"{settings.DEEPSEEK_API_BASE}/v1/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                logger.error(f"DEEPSEEK_API_ERROR: {{'request_id': '{request_id}', 'status': {response.status_code}, 'response': '{response.text}'}}")
                return {"action": "noop"}
            
            result = response.json()
            assistant_message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not assistant_message:
                logger.warning(f"DEEPSEEK_EMPTY_RESPONSE: {{'request_id': '{request_id}'}}")
                return {"action": "noop"}
            
            # Parse JSON response
            try:
                decision_data = json.loads(assistant_message.strip())
                logger.info(f"DEEPSEEK_RAW_RESPONSE: {{'request_id': '{request_id}', 'response': '{assistant_message}'}}")
                
                # Validate with Decision model
                decision = Decision(**decision_data)
                decision_dict = decision.dict()
                
                logger.info(f"DEEPSEEK_SUCCESS: {{'request_id': '{request_id}', 'decision': {decision_dict}}}")
                return decision_dict
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"DEEPSEEK_PARSE_ERROR: {{'request_id': '{request_id}', 'error': '{str(e)}', 'response': '{assistant_message}'}}")
                return {"action": "noop"}
                
    except asyncio.TimeoutError:
        logger.error(f"DEEPSEEK_TIMEOUT: {{'request_id': '{request_id}', 'timeout_ms': {settings.DEEPSEEK_TIMEOUT_MS}}}")
        return {"action": "noop"}
    except Exception as e:
        logger.error(f"DEEPSEEK_ERROR: {{'request_id': '{request_id}', 'error': '{str(e)}', 'type': '{type(e).__name__}'}}")
        return {"action": "noop"}

def build_context(
    status: Dict[str, Any],
    metrics: Dict[str, Any], 
    trades: list,
    positions: list,
    price: float,
    caps: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build compact context for DeepSeek decision making.
    
    Args:
        status: System status
        metrics: Portfolio metrics
        trades: Recent trades
        positions: Current positions
        price: Current price for default symbol
        caps: Trading caps and settings
        
    Returns:
        Compact context dictionary
    """
    return {
        "status": status,
        "metrics": metrics,
        "trades": trades[-10:] if trades else [],  # Last 10 trades
        "positions": positions,
        "price": price,
        "caps": caps,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    }
