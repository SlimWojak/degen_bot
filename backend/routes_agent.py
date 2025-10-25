"""
AI Agent routes for autonomous trading decisions.
"""

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.agent.deepseek_agent import call_deepseek, build_context, Decision
from backend.services.state_service import state_service
from backend.exchange.hl_private import hl_private_client
from backend.exchange.order_bus import order_bus
from backend.schemas.order_intent import OrderIntent, create_order_intent
from backend.util.live_guard import check_live_guard
from common.hl_client import connect, discover_price, place_ioc_limit_adaptive, usd_to_size

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory cooldown tracking
_last_decision_time = 0

def log_ai_decision(decision: Dict[str, Any], executed: bool, result: Dict[str, Any] = None):
    """Log AI decision to SQLite database."""
    try:
        conn = sqlite3.connect("data/ai_logs.db")
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                action TEXT,
                payload_json TEXT,
                executed BOOLEAN,
                result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert log entry
        cursor.execute("""
            INSERT INTO ai_logs (action, payload_json, executed, result_json)
            VALUES (?, ?, ?, ?)
        """, (
            decision.get("action", "unknown"),
            json.dumps(decision),
            executed,
            json.dumps(result) if result else None
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"AI decision logged: action={decision.get('action')}, executed={executed}")
    except Exception as e:
        logger.error(f"Failed to log AI decision: {e}")

@router.post("/decide_and_execute")
async def decide_and_execute(request: Request):
    """AI decision and execution endpoint with DeepSeek integration."""
    from backend.util.idempotency import check_duplicate, record_intent, generate_intent_id
    from backend.util.breakers import should_skip, get_all_status
    from backend.util.budget_guard import is_triggered as budget_triggered
    from backend.ai.deepseek_client import decide as deepseek_decide
    from backend.ai.context_builder import build_context
    from backend.services.sim_broker import get_sim_broker
    from backend.observability.logs import log_decision
    from backend.services.state_service import state_service
    
    global _last_decision_time
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Check for X-Intent-ID header
    intent_id = request.headers.get("X-Intent-ID")
    if not intent_id:
        intent_id = generate_intent_id()
    
    # Check for duplicate intent
    if check_duplicate(intent_id, "decide_and_execute"):
        logger.warning(f"Duplicate intent ID: {intent_id}")
        raise HTTPException(status_code=409, detail={"error": "Duplicate request", "intent_id": intent_id})
    
    # Record intent
    record_intent(intent_id, "decide_and_execute")
    
    # Rate limiting check
    current_time = time.time() * 1000
    if current_time - _last_decision_time < settings.AGENT_DECISION_COOLDOWN_MS:
        remaining_ms = settings.AGENT_DECISION_COOLDOWN_MS - (current_time - _last_decision_time)
        logger.warning(f"AGENT_RATE_LIMITED: {{'request_id': '{request_id}', 'remaining_ms': {remaining_ms}}}")
        raise HTTPException(status_code=429, detail={"error": f"Rate limited, try again in {remaining_ms:.0f}ms"})
    
    _last_decision_time = current_time
    
    logger.info(f"AGENT_DECISION_REQUEST: {{'request_id': '{request_id}', 'intent_id': '{intent_id}', 'client_ip': '{request.client.host if request.client else 'unknown'}'}}")
    
    try:
        # Check safety guards before AI call
        if should_skip("info") or should_skip("order"):
            logger.warning(f"Circuit breaker active, rejecting decision")
            raise HTTPException(status_code=423, detail={"error": "Circuit breaker active", "reason": "API failures"})
        
        if budget_triggered():
            logger.warning(f"Budget guard triggered, rejecting decision")
            raise HTTPException(status_code=423, detail={"error": "Budget guard triggered", "reason": "Daily loss limit exceeded"})
        
        # Check live guard
        from backend.util.live_guard import check_live_guard
        is_live_safe, guard_reason, guard_info = check_live_guard()
        execution_mode = "live" if is_live_safe else "sim"
        
        if not is_live_safe:
            logger.info(f"Live guard blocked: {guard_reason}")
            # Log the guard block
            from backend.observability.ai_health import record_ai_request
            record_ai_request(success=False, request_ms=0, rejected=True, mode="sim")
        
        # Parse request body
        body = await request.json()
        symbols = body.get("symbols", settings.AGENT_SYMBOLS.split(","))
        
        # Check for mock mode
        if body.get("mock"):
            # Return mock decision for testing
            mock_decision = {
                "action": "BUY",
                "symbol": "BTC",
                "notional_usd": 10.0,
                "reason": "mock test decision"
            }
            return {
                "decision": mock_decision,
                "execution": {
                    "result": "mock",
                    "reason": "Mock mode enabled"
                },
                "simulation": True
            }
        
        # Build context for DeepSeek
        try:
            # Get market data (non-blocking)
            market_data = {}
            for symbol in symbols:
                # This would get from market_ws in real implementation
                # For now, use mock data
                market_data[symbol] = {
                    "mid": 65000.0 if symbol == "BTC" else 3000.0,
                    "spread_bps": 5.0,
                    "obi": 0.5,
                    "rtn_5s": 0.001
                }
            
            context = build_context(symbols, market_data)
            
        except Exception as e:
            logger.error(f"Failed to build context: {e}")
            raise HTTPException(status_code=500, detail={"error": "Failed to build context", "reason": str(e)})
        
        # Call DeepSeek
        try:
            decision, telemetry = await deepseek_decide(context)
            
            if not decision:
                logger.error(f"DeepSeek decision failed: {telemetry.status}")
                raise HTTPException(status_code=422, detail={
                    "error": "Decision rejected",
                    "reason": telemetry.status,
                    "telemetry": {
                        "ai_request_ms": telemetry.ai_request_ms,
                        "retry_count": telemetry.retry_count,
                        "error_type": telemetry.error_type
                    }
                })
            
            # Apply guardrails
            if decision.notional_usd > settings.HL_MAX_NOTIONAL_USD:
                logger.warning(f"Decision notional clipped: {decision.notional_usd} -> {settings.HL_MAX_NOTIONAL_USD}")
                decision.notional_usd = settings.HL_MAX_NOTIONAL_USD
            
            # Apply adaptive notional clamp based on performance
            from backend.ai.reflection import should_clamp_notional
            from backend.observability.ai_health import record_adaptive_clamp
            
            original_notional = decision.notional_usd
            if should_clamp_notional():
                decision.notional_usd *= 0.5
                record_adaptive_clamp()
                logger.info(f"Adaptive clamp applied: {original_notional} -> {decision.notional_usd}")
            
            # Validate symbol
            if decision.symbol not in settings.AGENT_SYMBOLS.split(","):
                logger.warning(f"Unsupported symbol: {decision.symbol}")
                raise HTTPException(status_code=422, detail={"error": "Unsupported symbol", "symbol": decision.symbol})
            
            # Log the decision
            log_decision(
                symbol=decision.symbol,
                action=decision.action,
                notional=decision.notional_usd,
                reason=decision.reason,
                intent_id=intent_id
            )
            
            # Execute based on live guard and trading settings
            if not settings.HL_TRADING_ENABLED or execution_mode == "sim":
                sim_broker = get_sim_broker()
                trade = sim_broker.execute_order(
                    symbol=decision.symbol,
                    side=decision.action,
                    notional_usd=decision.notional_usd,
                    intent_id=intent_id
                )
                
                if trade:
                    # Update decision log with fill details
                    log_decision(
                        symbol=decision.symbol,
                        action=decision.action,
                        notional=decision.notional_usd,
                        reason=decision.reason,
                        intent_id=intent_id,
                        fill_px=trade.fill_px,
                        result="filled",
                        pnl_after=sim_broker.get_balance()["total_pnl"],
                        latency_ms=(time.time() - start_time) * 1000
                    )
                    
                    return {
                        "decision": decision.dict(),
                        "execution": {
                            "result": "filled",
                            "fill_px": trade.fill_px,
                            "slippage_bps": trade.slippage_bps,
                            "fee": trade.fee,
                            "latency_ms": (time.time() - start_time) * 1000
                        },
                        "simulation": True,
                        "mode": execution_mode,
                        "live_guard_blocked": not is_live_safe,
                        "telemetry": {
                            "ai_request_ms": telemetry.ai_request_ms,
                            "tokens": telemetry.tokens
                        }
                    }
                else:
                    return {
                        "decision": decision.dict(),
                        "execution": {
                            "result": "rejected",
                            "reason": "No market data available"
                        },
                        "simulation": True,
                        "mode": execution_mode,
                        "live_guard_blocked": not is_live_safe,
                        "telemetry": {
                            "ai_request_ms": telemetry.ai_request_ms,
                            "tokens": telemetry.tokens
                        }
                    }
            else:
                # Live trading mode (not implemented yet)
                return {
                    "decision": decision.dict(),
                    "execution": {
                        "result": "not_implemented",
                        "reason": "Live trading not yet implemented"
                    },
                    "simulation": False,
                    "mode": execution_mode,
                    "live_guard_blocked": not is_live_safe,
                    "telemetry": {
                        "ai_request_ms": telemetry.ai_request_ms,
                        "tokens": telemetry.tokens
                    }
                }
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DeepSeek call failed: {e}")
            raise HTTPException(status_code=500, detail={"error": "AI decision failed", "reason": str(e)})
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Decision execution failed: {e}")
        return {
            "error": str(e),
            "decision": body if 'body' in locals() else None,
            "execution": {
                "result": "error",
                "reason": str(e)
            }
        }

@router.get("/reflection/latest")
async def get_latest_reflection():
    """Get the latest reflection summary."""
    from backend.ai.reflection import get_latest_reflection
    
    try:
        reflection = get_latest_reflection()
        if not reflection:
            return {"error": "No reflection available"}
        
        return {
            "summary": reflection.get("summary_text", ""),
            "ts": reflection.get("ts"),
            "stats": {
                "trades": reflection.get("trades", 0),
                "wins": reflection.get("wins", 0),
                "losses": reflection.get("losses", 0),
                "win_rate": reflection.get("win_rate", 0.0),
                "total_pnl_usd": reflection.get("total_pnl_usd", 0.0),
                "avg_slippage_bps": reflection.get("avg_slippage_bps", 0.0),
                "policy_score": reflection.get("policy_score", 0.5)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get latest reflection: {e}")
        return {"error": str(e)}

@router.get("/logs")
async def get_ai_logs(limit: int = 50):
    """Get AI decision logs."""
    try:
        conn = sqlite3.connect("data/ai_logs.db")
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decided_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                action TEXT,
                payload_json TEXT,
                executed BOOLEAN,
                result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Query logs
        cursor.execute("""
            SELECT decided_at, action, payload_json, executed, result_json
            FROM ai_logs
            ORDER BY decided_at DESC
            LIMIT ?
        """, (limit,))
        
        logs = []
        for row in cursor.fetchall():
            decided_at, action, payload_json, executed, result_json = row
            
            # Parse payload and result
            try:
                payload = json.loads(payload_json) if payload_json else {}
                result = json.loads(result_json) if result_json else {}
            except json.JSONDecodeError:
                payload = {}
                result = {}
            
            logs.append({
                "decided_at": decided_at,
                "action": action,
                "payload": payload,
                "executed": bool(executed),
                "result": result
            })
        
        conn.close()
        return logs
        
    except Exception as e:
        logger.error(f"Failed to get AI logs: {e}")
        return []

@router.post("/submit_order")
async def submit_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit order intent with validation, risk management, and live guard.
    
    Args:
        order_data: Order intent data
        
    Returns:
        Order submission result with dry-run status and payload
    """
    try:
        # Create order intent
        order_intent = create_order_intent(
            symbol=order_data["symbol"],
            side=order_data["side"],
            size=float(order_data["size"]),
            order_type=order_data.get("type", "market"),
            limit_px=order_data.get("limit_px"),
            tif=order_data.get("tif", "GTC"),
            intent_id=order_data.get("intent_id"),
            meta=order_data.get("meta")
        )
        
        # Get current positions for risk calculation
        current_positions = {}  # Mock - would get from state service
        
        # Submit to order bus
        bus_result = await order_bus.submit(order_intent, current_positions)
        
        if not bus_result.success:
            if bus_result.idempotent:
                raise HTTPException(status_code=409, detail="Order intent already processed")
            else:
                raise HTTPException(status_code=422, detail=bus_result.error_message)
        
        # Check live guard
        is_live_safe, guard_reason, live_guard_status = check_live_guard()
        is_live_allowed = is_live_safe
        
        # Build order payload
        order_payload = hl_private_client.build_order(order_intent.dict())
        
        # Determine execution mode
        if is_live_allowed and settings.HL_TRADING_ENABLED:
            mode = "live"
            dry_run = False
        else:
            mode = "sim"
            dry_run = True
        
        # Send order (dry-run if not live)
        send_result = await hl_private_client.send_order(order_payload, dry_run=dry_run)
        
        # Update order status
        if send_result.success:
            await order_bus.update_order_status(
                bus_result.order_id,
                "submitted",
                {"mode": mode, "dry_run": dry_run}
            )
        else:
            await order_bus.update_order_status(
                bus_result.order_id,
                "failed",
                {"error": send_result.error_message}
            )
        
        # Prepare response
        response = {
            "success": send_result.success,
            "mode": mode,
            "dry_run": dry_run,
            "order_id": bus_result.order_id,
            "intent_id": order_intent.intent_id,
            "would_send": order_payload if dry_run else None,
            "guards": {
                "live_guard": live_guard_status,
                "trading_enabled": settings.HL_TRADING_ENABLED
            },
            "validation": bus_result.validation_result.dict() if bus_result.validation_result else None
        }
        
        if not send_result.success:
            response["error"] = send_result.error_message
        
        logger.info(f"[agent] Order submitted: {order_intent.symbol} {order_intent.side} {order_intent.size} ({mode})")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[agent] Order submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
