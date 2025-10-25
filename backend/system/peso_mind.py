"""
PesoMind - Global orchestrator for the reasoning-execution-reflection triad.
Coordinates the thinking core of PesoEcho.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.agents.reasoning_engine import reasoning_engine
from backend.agents.trade_kernel import trade_kernel
from backend.agents.learning_loop import learning_loop

logger = logging.getLogger("peso_mind")

class PesoMind:
    """Global orchestrator for the AI trading system."""
    
    def __init__(self):
        self.mind_mode = os.getenv("MIND_MODE", "SIM")  # SIM | LIVE
        self.llm_provider = os.getenv("LLM_PROVIDER", "mock")  # local|openai|none
        self.cycle_interval = int(os.getenv("MIND_CYCLE_INTERVAL", "300"))  # 5 minutes
        self.running = False
        self.cycle_count = 0
        self.last_cycle_time: Optional[datetime] = None
        
        # Status tracking
        self.status = {
            "running": False,
            "mode": self.mind_mode,
            "llm_provider": self.llm_provider,
            "cycle_count": 0,
            "last_cycle": None,
            "next_cycle": None
        }
    
    async def start(self) -> None:
        """Start the PesoMind orchestrator."""
        if self.running:
            logger.warning("[peso_mind] Already running")
            return
        
        self.running = True
        self.status["running"] = True
        
        # Start background cycle loop
        asyncio.create_task(self._cycle_loop())
        
        logger.info(f"[peso_mind] Started in {self.mind_mode} mode with {self.llm_provider} LLM")
    
    async def stop(self) -> None:
        """Stop the PesoMind orchestrator."""
        self.running = False
        self.status["running"] = False
        logger.info("[peso_mind] Stopped")
    
    async def _cycle_loop(self) -> None:
        """Main cycle loop for reasoning-execution-reflection."""
        while self.running:
            try:
                await self._execute_cycle()
                await asyncio.sleep(self.cycle_interval)
            except Exception as e:
                logger.error(f"[peso_mind] Cycle error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _execute_cycle(self) -> None:
        """Execute one complete reasoning-execution-reflection cycle."""
        cycle_start = datetime.now(timezone.utc)
        self.cycle_count += 1
        
        logger.info(f"[peso_mind] Starting cycle #{self.cycle_count}")
        
        try:
            # Step 1: Reasoning
            reasoning_result = await self._reasoning_step()
            
            # Step 2: Execution (if conditions met)
            execution_result = await self._execution_step(reasoning_result)
            
            # Step 3: Reflection (every 5 cycles or on significant events)
            reflection_result = None
            if self.cycle_count % 5 == 0 or execution_result.get("trade_executed"):
                reflection_result = await self._reflection_step()
            
            # Update status
            self.last_cycle_time = cycle_start
            self.status["last_cycle"] = cycle_start.isoformat()
            self.status["next_cycle"] = (cycle_start.timestamp() + self.cycle_interval)
            self.status["cycle_count"] = self.cycle_count
            
            cycle_duration = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            logger.info(f"[peso_mind] Cycle #{self.cycle_count} completed in {cycle_duration:.1f}s")
            
        except Exception as e:
            logger.error(f"[peso_mind] Cycle #{self.cycle_count} failed: {e}")
    
    async def _reasoning_step(self) -> Dict[str, Any]:
        """Execute reasoning step."""
        try:
            # Get market context (mock for now)
            context = await self._get_market_context()
            
            # Run reasoning engine
            analysis = await reasoning_engine.analyze(context)
            
            logger.info(f"[peso_mind] Reasoning: {analysis['symbol']} {analysis['trend_bias']} (conf: {analysis['confidence']:.2f})")
            
            return {
                "step": "reasoning",
                "analysis": analysis,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[peso_mind] Reasoning step failed: {e}")
            return {
                "step": "reasoning",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _execution_step(self, reasoning_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute trading step."""
        try:
            if "error" in reasoning_result:
                return {
                    "step": "execution",
                    "skipped": True,
                    "reason": "Reasoning failed",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            analysis = reasoning_result.get("analysis", {})
            
            # Check if we should execute a trade
            if analysis.get("confidence", 0) >= 0.7:  # High confidence threshold
                # Create trade decision
                trade_decision = {
                    "symbol": analysis.get("symbol", "BTC"),
                    "side": "buy" if analysis.get("trend_bias") == "bullish" else "sell",
                    "size": 1.0,  # Fixed size for now
                    "confidence": analysis.get("confidence", 0.5),
                    "reason": analysis.get("rationale", "High confidence signal")
                }
                
                # Execute trade
                execution_result = await trade_kernel.execute(trade_decision)
                
                logger.info(f"[peso_mind] Execution: {execution_result['status']}")
                
                return {
                    "step": "execution",
                    "trade_executed": execution_result["status"] == "executed",
                    "execution_result": execution_result,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            else:
                logger.info(f"[peso_mind] Execution: Skipped (confidence {analysis.get('confidence', 0):.2f} < 0.7)")
                return {
                    "step": "execution",
                    "skipped": True,
                    "reason": "Low confidence",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error(f"[peso_mind] Execution step failed: {e}")
            return {
                "step": "execution",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _reflection_step(self) -> Dict[str, Any]:
        """Execute reflection step."""
        try:
            # Run learning loop
            reflection_result = await learning_loop.reflect("BTC")
            
            logger.info(f"[peso_mind] Reflection: {reflection_result['status']}")
            
            return {
                "step": "reflection",
                "reflection_result": reflection_result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[peso_mind] Reflection step failed: {e}")
            return {
                "step": "reflection",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _get_market_context(self) -> Dict[str, Any]:
        """Get market context for reasoning (mock implementation)."""
        # Mock market data - in real implementation, would get from sampler
        import random
        
        return {
            "symbol": "BTC",
            "price": 50000 + random.randint(-1000, 1000),
            "price_change_24h": random.randint(-2000, 2000),
            "funding_rate": random.uniform(-0.01, 0.01),
            "open_interest": random.randint(1000000, 5000000),
            "volume_24h": random.randint(100000, 500000),
            "spread_bps": random.uniform(0.1, 0.5),
            "last_update": datetime.now(timezone.utc).isoformat()
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current PesoMind status."""
        return self.status.copy()
    
    def get_positions(self) -> Dict[str, float]:
        """Get current positions from trade kernel."""
        return trade_kernel.get_positions()
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary from learning loop."""
        return learning_loop.get_performance_summary()
    
    async def manual_cycle(self) -> Dict[str, Any]:
        """Manually trigger one cycle."""
        if not self.running:
            return {"error": "PesoMind not running"}
        
        try:
            await self._execute_cycle()
            return {"status": "completed", "cycle_count": self.cycle_count}
        except Exception as e:
            return {"error": str(e)}

# Global PesoMind instance
peso_mind = PesoMind()
