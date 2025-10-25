"""
DeepSeek AI client for decision making.
Implements strict JSON tool contract with retry logic and telemetry.
"""

import json
import time
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import aiohttp
from backend.config import settings
from backend.schemas.simulation import DeepSeekDecision

logger = logging.getLogger(__name__)

@dataclass
class DecisionTelemetry:
    """Telemetry for AI decision requests."""
    ai_request_ms: float
    status: str
    tokens: Optional[int] = None
    retry_count: int = 0
    error_type: Optional[str] = None

class DeepSeekClient:
    """DeepSeek AI client with strict JSON schema enforcement."""
    
    def __init__(self):
        self.api_base = settings.DEEPSEEK_API_BASE
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model = settings.DEEPSEEK_MODEL
        self.timeout_ms = settings.DEEPSEEK_TIMEOUT_MS
        self.max_retries = getattr(settings, 'DECISION_RETRY_MAX', 2)
        self.retry_base_ms = getattr(settings, 'DECISION_RETRY_BASE_MS', 250)
        
    async def decide(self, context: str) -> Tuple[Optional[DeepSeekDecision], DecisionTelemetry]:
        """
        Make decision using DeepSeek with strict JSON schema.
        
        Args:
            context: Formatted context string for the model
            
        Returns:
            Tuple of (decision, telemetry)
        """
        start_time = time.time()
        telemetry = DecisionTelemetry(
            ai_request_ms=0.0,
            status="pending",
            retry_count=0
        )
        
        for attempt in range(self.max_retries + 1):
            try:
                # Build the prompt with strict JSON schema
                prompt = self._build_prompt(context)
                
                # Make API call
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    payload = {
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a trading AI. Return ONLY valid JSON matching the exact schema. No prose or explanations."
                            },
                            {
                                "role": "user", 
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 200
                    }
                    
                    timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
                    
                    async with session.post(
                        f"{self.api_base}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    ) as response:
                        
                        response_data = await response.json()
                        
                        if response.status == 200:
                            # Parse response
                            content = response_data["choices"][0]["message"]["content"].strip()
                            
                            # Validate JSON schema
                            decision = self._parse_decision(content)
                            
                            if decision:
                                telemetry.ai_request_ms = (time.time() - start_time) * 1000
                                telemetry.status = "success"
                                telemetry.tokens = response_data.get("usage", {}).get("total_tokens")
                                telemetry.retry_count = attempt
                                
                                logger.info(f"DeepSeek decision successful: {decision.dict()}")
                                return decision, telemetry
                            else:
                                # Invalid JSON, try reprompt
                                if attempt < self.max_retries:
                                    logger.warning(f"Invalid JSON on attempt {attempt + 1}, retrying...")
                                    await asyncio.sleep(self.retry_base_ms * (2 ** attempt) / 1000.0)
                                    continue
                                else:
                                    telemetry.status = "invalid_json"
                                    telemetry.error_type = "malformed_response"
                                    logger.error(f"Failed to parse valid JSON after {self.max_retries + 1} attempts")
                                    return None, telemetry
                        else:
                            # HTTP error
                            error_msg = f"HTTP {response.status}: {response_data.get('error', {}).get('message', 'Unknown error')}"
                            telemetry.error_type = f"http_{response.status}"
                            
                            if response.status >= 500 and attempt < self.max_retries:
                                # Retry on server errors
                                logger.warning(f"Server error on attempt {attempt + 1}: {error_msg}")
                                await asyncio.sleep(self.retry_base_ms * (2 ** attempt) / 1000.0)
                                continue
                            else:
                                telemetry.status = "http_error"
                                logger.error(f"HTTP error: {error_msg}")
                                return None, telemetry
                                
            except asyncio.TimeoutError:
                telemetry.error_type = "timeout"
                if attempt < self.max_retries:
                    logger.warning(f"Timeout on attempt {attempt + 1}, retrying...")
                    await asyncio.sleep(self.retry_base_ms * (2 ** attempt) / 1000.0)
                    continue
                else:
                    telemetry.status = "timeout"
                    logger.error(f"Request timeout after {self.max_retries + 1} attempts")
                    return None, telemetry
                    
            except Exception as e:
                telemetry.error_type = "exception"
                telemetry.status = "error"
                logger.error(f"Unexpected error in DeepSeek call: {e}")
                return None, telemetry
        
        telemetry.ai_request_ms = (time.time() - start_time) * 1000
        return None, telemetry
    
    def _build_prompt(self, context: str) -> str:
        """Build the prompt for DeepSeek with strict JSON schema."""
        return f"""Analyze the trading context and make a decision. Return ONLY valid JSON matching this exact schema:

{{
  "action": "BUY|SELL|HOLD",
  "symbol": "BTC|ETH|SOL|DOGE|XRP|HYPE", 
  "notional_usd": 1.0-1000.0,
  "reason": "5-200 character explanation"
}}

Context:
{context}

Return ONLY the JSON object, no other text."""

    def _parse_decision(self, content: str) -> Optional[DeepSeekDecision]:
        """Parse and validate decision from DeepSeek response."""
        try:
            # Clean the content
            content = content.strip()
            
            # Remove any markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            content = content.strip()
            
            # Parse JSON
            data = json.loads(content)
            
            # Validate using Pydantic schema
            decision = DeepSeekDecision(**data)
            
            return decision
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.warning(f"Decision validation error: {e}")
            return None

# Global client instance
_deepseek_client = DeepSeekClient()

async def decide(context: str) -> Tuple[Optional[DeepSeekDecision], DecisionTelemetry]:
    """Make a decision using DeepSeek."""
    return await _deepseek_client.decide(context)
