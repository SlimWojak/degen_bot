"""
Mind Control API - Endpoints for reasoning, execution, and reflection.
Provides control interface for the PesoMind orchestrator.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from backend.system.peso_mind import peso_mind
from backend.agents.reasoning_engine import reasoning_engine
from backend.agents.trade_kernel import trade_kernel
from backend.agents.learning_loop import learning_loop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ops", tags=["mind-control"])

@router.get("/mind-status")
async def get_mind_status() -> Dict[str, Any]:
    """Get current PesoMind status."""
    try:
        status = peso_mind.get_status()
        positions = peso_mind.get_positions()
        performance = peso_mind.get_performance_summary()
        
        return {
            "mind": status,
            "positions": positions,
            "performance": performance
        }
    except Exception as e:
        logger.error(f"Failed to get mind status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reason")
async def trigger_reasoning() -> Dict[str, Any]:
    """Trigger manual reasoning analysis."""
    try:
        # Get mock market context
        context = {
            "symbol": "BTC",
            "price": 50000,
            "price_change_24h": 1000,
            "funding_rate": 0.001,
            "open_interest": 2000000,
            "volume_24h": 300000,
            "spread_bps": 0.2,
            "last_update": "2025-01-25T13:00:00Z"
        }
        
        # Run reasoning
        analysis = await reasoning_engine.analyze(context)
        
        return {
            "status": "completed",
            "analysis": analysis
        }
    except Exception as e:
        logger.error(f"Reasoning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/decide")
async def trigger_decision() -> Dict[str, Any]:
    """Trigger one complete reasoning → execution → log cycle."""
    try:
        # Get reasoning
        context = {
            "symbol": "BTC",
            "price": 50000,
            "price_change_24h": 1000,
            "funding_rate": 0.001,
            "open_interest": 2000000,
            "volume_24h": 300000,
            "spread_bps": 0.2,
            "last_update": "2025-01-25T13:00:00Z"
        }
        
        analysis = await reasoning_engine.analyze(context)
        
        # Create trade decision if confidence is high enough
        if analysis.get("confidence", 0) >= 0.7:
            trade_decision = {
                "symbol": analysis.get("symbol", "BTC"),
                "side": "buy" if analysis.get("trend_bias") == "bullish" else "sell",
                "size": 1.0,
                "confidence": analysis.get("confidence", 0.5),
                "reason": analysis.get("rationale", "High confidence signal")
            }
            
            execution_result = await trade_kernel.execute(trade_decision)
            
            return {
                "status": "completed",
                "reasoning": analysis,
                "execution": execution_result
            }
        else:
            return {
                "status": "completed",
                "reasoning": analysis,
                "execution": {"status": "skipped", "reason": "Low confidence"}
            }
    except Exception as e:
        logger.error(f"Decision failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reflect")
async def trigger_reflection() -> Dict[str, Any]:
    """Trigger manual reflection cycle."""
    try:
        reflection_result = await learning_loop.reflect("BTC")
        
        return {
            "status": "completed",
            "reflection": reflection_result
        }
    except Exception as e:
        logger.error(f"Reflection failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades")
async def get_trades(limit: int = 20) -> Dict[str, Any]:
    """Get recent trade history."""
    try:
        trades = trade_kernel.get_trade_history(limit=limit)
        
        return {
            "trades": trades,
            "count": len(trades)
        }
    except Exception as e:
        logger.error(f"Failed to get trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reflections")
async def get_reflections(limit: int = 10) -> Dict[str, Any]:
    """Get reflection history."""
    try:
        reflections = learning_loop.get_reflection_history(limit=limit)
        performance_summary = learning_loop.get_performance_summary()
        
        return {
            "reflections": reflections,
            "count": len(reflections),
            "performance_summary": performance_summary
        }
    except Exception as e:
        logger.error(f"Failed to get reflections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mind-start")
async def start_mind() -> Dict[str, Any]:
    """Start the PesoMind orchestrator."""
    try:
        await peso_mind.start()
        return {"status": "started", "message": "PesoMind orchestrator started"}
    except Exception as e:
        logger.error(f"Failed to start mind: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mind-stop")
async def stop_mind() -> Dict[str, Any]:
    """Stop the PesoMind orchestrator."""
    try:
        await peso_mind.stop()
        return {"status": "stopped", "message": "PesoMind orchestrator stopped"}
    except Exception as e:
        logger.error(f"Failed to stop mind: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mind-cycle")
async def manual_cycle() -> Dict[str, Any]:
    """Manually trigger one mind cycle."""
    try:
        result = await peso_mind.manual_cycle()
        return result
    except Exception as e:
        logger.error(f"Manual cycle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
