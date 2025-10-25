"""
Degen God v2 Autonomous Learning Memory System.

Handles DeepSeek learning, rule updates, and memory management
for continuous strategy improvement.
"""

import asyncio
import os
import logging
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


class LearningMemory:
    """Autonomous learning memory system for DeepSeek."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the learning memory system.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.memory_path = os.getenv("MEMORY_PATH", "memory")
        self.rules_file = os.path.join(self.memory_path, "rules.txt")
        self.deepseek_api_key = config.get("deepseek", {}).get("api_key")
        
        # Ensure memory directory exists
        os.makedirs(self.memory_path, exist_ok=True)
        
        # Load existing rules
        self.rules = self._load_rules()
        
    def _load_rules(self) -> List[str]:
        """
        Load existing rules from file.
        
        Returns:
            List of rule strings
        """
        try:
            if os.path.exists(self.rules_file):
                with open(self.rules_file, 'r') as f:
                    rules = [line.strip() for line in f.readlines() if line.strip()]
                logger.info(f"📚 Loaded {len(rules)} rules from memory")
                return rules
            else:
                logger.info("📚 No existing rules found, starting fresh")
                return []
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
            return []
    
    def _save_rules(self) -> None:
        """Save rules to file."""
        try:
            with open(self.rules_file, 'w') as f:
                for rule in self.rules:
                    f.write(f"{rule}\n")
            logger.info(f"💾 Saved {len(self.rules)} rules to memory")
        except Exception as e:
            logger.error(f"Error saving rules: {e}")
    
    def _truncate_rules(self) -> None:
        """Keep only the best 3 rules to stay under 300 tokens."""
        if len(self.rules) > 3:
            # Keep the most recent 3 rules
            self.rules = self.rules[-3:]
            logger.info("✂️  Truncated rules to top 3 (300 token limit)")
    
    async def get_memory_context(self, recent_trades: List[Dict[str, Any]]) -> str:
        """
        Generate memory context for DeepSeek prompt injection.
        
        Args:
            recent_trades: List of recent trade data
            
        Returns:
            Formatted memory context string
        """
        try:
            context_parts = []
            
            # Add recent trades context
            if recent_trades:
                context_parts.append("Recent trades:")
                for i, trade in enumerate(recent_trades[:5], 1):
                    asset = trade.get('asset', 'N/A')
                    action = trade.get('action', 'N/A')
                    score = trade.get('score', 0)
                    pnl_pct = trade.get('pnl_pct', 0)
                    reason = trade.get('reason', '')
                    
                    # Format trade summary
                    trade_summary = f"Trade{i}: {score} score {action} {asset} {pnl_pct:+.1f}%"
                    if reason:
                        trade_summary += f" ({reason})"
                    
                    context_parts.append(trade_summary)
            
            # Add learned rules
            if self.rules:
                context_parts.append("\nLearned rules:")
                for rule in self.rules:
                    context_parts.append(f"- {rule}")
            
            # Add pattern analysis
            if len(recent_trades) >= 3:
                pattern = self._analyze_patterns(recent_trades)
                if pattern:
                    context_parts.append(f"\nPattern: {pattern}")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Error generating memory context: {e}")
            return ""
    
    def _analyze_patterns(self, trades: List[Dict[str, Any]]) -> str:
        """
        Analyze patterns in recent trades with enhanced pattern recognition.
        
        Args:
            trades: List of recent trades
            
        Returns:
            Pattern description string
        """
        try:
            if len(trades) < 3:
                return ""
            
            # Analyze win/loss patterns
            wins = [t for t in trades if t.get('pnl_pct', 0) > 0]
            losses = [t for t in trades if t.get('pnl_pct', 0) < 0]
            
            patterns = []
            
            # Volume vs momentum pattern (enhanced)
            vol_traps = [t for t in losses if t.get('ind_vol', 0) > 250 and t.get('ind_mom', 0) < 12]
            if vol_traps:
                patterns.append("Skip vol>2.5x if mom<12%")
            
            # RSI oversold pattern (enhanced)
            rsi_wins = [t for t in wins if t.get('ind_rsi', 50) < 30]
            if rsi_wins:
                patterns.append("RSI<30 often leads to wins")
            
            # High score pattern (enhanced)
            high_score_wins = [t for t in wins if t.get('score', 0) > 90]
            if high_score_wins:
                patterns.append("Score>90 has high win rate")
            
            # Low momentum losses
            low_mom_losses = [t for t in losses if t.get('ind_mom', 0) < 8]
            if low_mom_losses:
                patterns.append("Tighten SL on low mom")
            
            # High volume wins
            high_vol_wins = [t for t in wins if t.get('ind_vol', 0) > 200]
            if high_vol_wins:
                patterns.append("High vol often confirms moves")
            
            return ". ".join(patterns) if patterns else ""
            
        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            return ""
    
    async def reflect_on_trade(self, trade_data: Dict[str, Any]) -> Optional[str]:
        """
        Reflect on a completed trade and generate learning insights.
        
        Args:
            trade_data: Completed trade data
            
        Returns:
            Generated rule update or None
        """
        try:
            if not self.deepseek_api_key:
                logger.warning("No DeepSeek API key for reflection")
                return None
            
            # Prepare reflection prompt
            score = trade_data.get('score', 0)
            action = trade_data.get('action', 'N/A')
            asset = trade_data.get('asset', 'N/A')
            pnl_pct = trade_data.get('pnl_pct', 0)
            rsi = trade_data.get('ind_rsi', 0)
            mom = trade_data.get('ind_mom', 0)
            vol = trade_data.get('ind_vol', 0)
            
            reflection_prompt = f"""Review: Score {score}, {action} {asset}, PnL {pnl_pct:.1f}%. 
Data: RSI={rsi:.1f}, mom={mom:.1f}%, vol={vol:.1f}%. 
Why win/loss? Output: 1-line rule update (e.g., 'Reduce lev to 25x when RSI<25')."""
            
            # Query DeepSeek for reflection
            rule_update = await self._query_deepseek_reflection(reflection_prompt)
            
            if rule_update:
                # Add new rule
                self.rules.append(rule_update)
                self._truncate_rules()
                self._save_rules()
                
                logger.info(f"🧠 DeepSeek learned: {rule_update}")
                return rule_update
            
            return None
            
        except Exception as e:
            logger.error(f"Error reflecting on trade: {e}")
            return None
    
    async def _query_deepseek_reflection(self, prompt: str) -> Optional[str]:
        """
        Query DeepSeek for trade reflection.
        
        Args:
            prompt: Reflection prompt
            
        Returns:
            Generated rule or None
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.deepseek_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 100
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    logger.error(f"DeepSeek reflection error: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error querying DeepSeek reflection: {e}")
            return None
    
    async def get_learning_summary(self) -> str:
        """
        Get a summary of learned rules and patterns.
        
        Returns:
            Learning summary string
        """
        try:
            if not self.rules:
                return "No learning data available yet."
            
            summary_parts = []
            summary_parts.append(f"🧠 DeepSeek has learned {len(self.rules)} rules:")
            
            for i, rule in enumerate(self.rules, 1):
                summary_parts.append(f"   {i}. {rule}")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error generating learning summary: {e}")
            return "Error generating learning summary."
    
    async def reset_memory(self) -> None:
        """Reset learning memory."""
        try:
            self.rules = []
            self._save_rules()
            logger.info("🔄 Learning memory reset")
        except Exception as e:
            logger.error(f"Error resetting memory: {e}")
    
    def get_rules(self) -> List[str]:
        """Get current rules."""
        return self.rules.copy()
    
    def add_rule(self, rule: str) -> None:
        """Add a new rule manually."""
        try:
            self.rules.append(rule)
            self._truncate_rules()
            self._save_rules()
            logger.info(f"📝 Added rule: {rule}")
        except Exception as e:
            logger.error(f"Error adding rule: {e}")
