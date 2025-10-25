"""
Degen God v2 World-Class Logging System.

Handles SQLite database logging, equity curve plotting,
and arena-style statistics for autonomous trading.
"""

import asyncio
import sqlite3
import os
import logging
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeLogger:
    """World-class trade logging with SQLite database and analytics."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the trade logger.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.db_path = os.getenv("DB_PATH", "data/trades.db")
        self.plots_path = os.getenv("PLOTS_PATH", "plots")
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.plots_path, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Track equity curve
        self.equity_curve = []
        self.last_plot_trade_count = 0
        
    def _init_database(self) -> None:
        """Initialize SQLite database with trades table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create trades table with enhanced schema
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts INTEGER NOT NULL,
                        asset TEXT NOT NULL,
                        action TEXT NOT NULL,
                        score INTEGER NOT NULL,
                        entry_px REAL NOT NULL,
                        size_usd REAL NOT NULL,
                        lev INTEGER NOT NULL,
                        tp REAL NOT NULL,
                        sl REAL NOT NULL,
                        exit_px REAL,
                        pnl_usd REAL,
                        pnl_pct REAL,
                        duration_s INTEGER,
                        reason TEXT,
                        ind_rsi REAL,
                        ind_macd REAL,
                        ind_mom REAL,
                        ind_vol REAL,
                        ind_atr REAL,
                        win INTEGER,
                        deepseek_prompt TEXT,
                        reflection_rule TEXT,
                        sharpe REAL,
                        max_dd REAL
                    )
                """)
                
                # Create equity_curve table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS equity_curve (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        total_value REAL NOT NULL
                    )
                """)
                
                # Create index for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_ts ON trades(ts)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_asset ON trades(asset)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_win ON trades(win)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_equity_timestamp ON equity_curve(timestamp)")
                
                conn.commit()
                logger.info(f"✅ Database initialized with trades and equity_curve tables: {self.db_path}")
                
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    async def log_trade(self, trade_data: Dict[str, Any]) -> bool:
        """
        Log a completed trade to the database.
        
        Args:
            trade_data: Dictionary with trade information
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Calculate running stats
                current_sharpe = await self.get_sharpe_ratio()
                current_max_dd = await self.get_max_drawdown()
                
                # Insert trade record with enhanced fields
                cursor.execute("""
                    INSERT INTO trades (
                        ts, asset, action, score, entry_px, size_usd, lev,
                        tp, sl, exit_px, pnl_usd, pnl_pct, duration_s,
                        reason, ind_rsi, ind_macd, ind_mom, ind_vol, ind_atr, win,
                        deepseek_prompt, reflection_rule, sharpe, max_dd
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade_data.get('timestamp', int(datetime.now().timestamp())),
                    trade_data.get('asset', ''),
                    trade_data.get('action', ''),
                    trade_data.get('score', 0),
                    trade_data.get('entry_px', 0.0),
                    trade_data.get('size_usd', 0.0),
                    trade_data.get('lev', 1),
                    trade_data.get('tp', 0.0),
                    trade_data.get('sl', 0.0),
                    trade_data.get('exit_px', 0.0),
                    trade_data.get('pnl_usd', 0.0),
                    trade_data.get('pnl_pct', 0.0),
                    trade_data.get('duration_s', 0),
                    trade_data.get('reason', ''),
                    trade_data.get('ind_rsi', 0.0),
                    trade_data.get('ind_macd', 0.0),
                    trade_data.get('ind_mom', 0.0),
                    trade_data.get('ind_vol', 0.0),
                    trade_data.get('ind_atr', 0.0),
                    trade_data.get('win', 0),
                    trade_data.get('deepseek_prompt', ''),
                    trade_data.get('reflection_rule', ''),
                    current_sharpe,
                    current_max_dd
                ))
                
                conn.commit()
                
                # Update equity curve
                await self._update_equity_curve(trade_data)
                
                # Check if we should plot equity curve
                total_trades = await self._get_total_trades()
                if total_trades - self.last_plot_trade_count >= 5:
                    await self._plot_equity_curve()
                    self.last_plot_trade_count = total_trades
                
                logger.info(f"✅ Trade logged: {trade_data.get('asset', 'N/A')} {trade_data.get('action', 'N/A')} "
                          f"PnL: {trade_data.get('pnl_pct', 0):.2f}%")
                return True
                
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
            return False
    
    async def _update_equity_curve(self, trade_data: Dict[str, Any]) -> None:
        """Update equity curve with new trade data."""
        try:
            pnl_usd = trade_data.get('pnl_usd', 0.0)
            current_equity = self.equity_curve[-1] if self.equity_curve else self.config.get('bot', {}).get('start_capital', 10000)
            new_equity = current_equity + pnl_usd
            self.equity_curve.append(new_equity)
            
        except Exception as e:
            logger.error(f"Error updating equity curve: {e}")
    
    async def _get_total_trades(self) -> int:
        """Get total number of trades in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM trades")
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting total trades: {e}")
            return 0
    
    async def _plot_equity_curve(self) -> None:
        """Plot and save equity curve."""
        try:
            if len(self.equity_curve) < 2:
                return
            
            plt.figure(figsize=(12, 6))
            plt.plot(self.equity_curve, linewidth=2, color='#00CFFF')
            plt.title('Degen God v2 - Equity Curve', fontsize=16, fontweight='bold')
            plt.xlabel('Trade Number', fontsize=12)
            plt.ylabel('Portfolio Value ($)', fontsize=12)
            plt.grid(True, alpha=0.3)
            
            # Add performance metrics
            total_return = (self.equity_curve[-1] - self.equity_curve[0]) / self.equity_curve[0] * 100
            plt.text(0.02, 0.98, f'Total Return: {total_return:.1f}%', 
                    transform=plt.gca().transAxes, fontsize=10, 
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue", alpha=0.7),
                    verticalalignment='top')
            
            plt.tight_layout()
            plt.savefig(f"{self.plots_path}/equity.png", dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"📊 Equity curve plotted: {self.plots_path}/equity.png")
            
        except Exception as e:
            logger.error(f"Error plotting equity curve: {e}")
    
    async def get_win_rate(self, last_n: int = 20) -> float:
        """
        Calculate win rate for last N trades.
        
        Args:
            last_n: Number of recent trades to analyze
            
        Returns:
            Win rate percentage
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT AVG(win) * 100 
                    FROM (
                        SELECT win FROM trades 
                        ORDER BY ts DESC 
                        LIMIT ?
                    )
                """, (last_n,))
                
                result = cursor.fetchone()
                return float(result[0]) if result[0] is not None else 0.0
                
        except Exception as e:
            logger.error(f"Error calculating win rate: {e}")
            return 0.0
    
    async def get_sharpe_ratio(self) -> float:
        """
        Calculate Sharpe ratio from PnL series.
        
        Returns:
            Sharpe ratio
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT pnl_pct FROM trades WHERE pnl_pct IS NOT NULL ORDER BY ts")
                
                pnl_series = [row[0] for row in cursor.fetchall()]
                
                if len(pnl_series) < 2:
                    return 0.0
                
                # Calculate Sharpe ratio
                mean_return = np.mean(pnl_series)
                std_return = np.std(pnl_series)
                
                if std_return == 0:
                    return 0.0
                
                sharpe = mean_return / std_return
                return float(sharpe)
                
        except Exception as e:
            logger.error(f"Error calculating Sharpe ratio: {e}")
            return 0.0
    
    async def get_max_drawdown(self) -> float:
        """
        Calculate maximum drawdown from equity curve.
        
        Returns:
            Maximum drawdown percentage
        """
        try:
            if len(self.equity_curve) < 2:
                return 0.0
            
            # Calculate running maximum
            running_max = np.maximum.accumulate(self.equity_curve)
            
            # Calculate drawdown
            drawdown = (self.equity_curve - running_max) / running_max * 100
            
            # Return maximum drawdown
            max_dd = np.min(drawdown)
            return float(max_dd)
            
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0
    
    async def get_last_25_trades(self) -> List[Dict[str, Any]]:
        """
        Get last 25 trades for dashboard display.
        
        Returns:
            List of trade dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, ts, asset, action, score, entry_px, exit_px, pnl_pct, 
                           duration_s, reason, ind_rsi, ind_mom, ind_vol, win, deepseek_prompt, reflection_rule
                    FROM trades 
                    ORDER BY ts DESC 
                    LIMIT 25
                """)
                
                trades = []
                for row in cursor.fetchall():
                    trades.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'asset': row[2],
                        'action': row[3],
                        'score': row[4],
                        'entry_px': row[5],
                        'exit_px': row[6],
                        'pnl_pct': row[7],
                        'duration_s': row[8],
                        'reason': row[9],
                        'ind_rsi': row[10],
                        'ind_mom': row[11],
                        'ind_vol': row[12],
                        'win': row[13],
                        'deepseek_prompt': row[14],
                        'reflection_rule': row[15]
                    })
                
                return trades
                
        except Exception as e:
            logger.error(f"Error getting last 25 trades: {e}")
            return []
    
    async def get_last_14_trades(self) -> List[Dict[str, Any]]:
        """
        Get last 14 trades for DeepSeek learning.
        
        Returns:
            List of trade dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT asset, action, score, pnl_pct, reason, ind_rsi, ind_mom, ind_vol
                    FROM trades 
                    ORDER BY ts DESC 
                    LIMIT 14
                """)
                
                trades = []
                for row in cursor.fetchall():
                    trades.append({
                        'asset': row[0],
                        'action': row[1],
                        'score': row[2],
                        'pnl_pct': row[3],
                        'reason': row[4],
                        'ind_rsi': row[5],
                        'ind_mom': row[6],
                        'ind_vol': row[7]
                    })
                
                return trades
                
        except Exception as e:
            logger.error(f"Error getting last 14 trades: {e}")
            return []
    
    async def get_last_5_trades(self) -> List[Dict[str, Any]]:
        """
        Get last 5 trades for DeepSeek memory injection.
        
        Returns:
            List of trade dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT asset, action, score, pnl_pct, reason, ind_mom, ind_vol
                    FROM trades 
                    ORDER BY ts DESC 
                    LIMIT 5
                """)
                
                trades = []
                for row in cursor.fetchall():
                    trades.append({
                        'asset': row[0],
                        'action': row[1],
                        'score': row[2],
                        'pnl_pct': row[3],
                        'reason': row[4],
                        'ind_mom': row[5],
                        'ind_vol': row[6]
                    })
                
                return trades
                
        except Exception as e:
            logger.error(f"Error getting last 5 trades: {e}")
            return []
    
    async def print_arena_stats(self) -> None:
        """Print arena-style statistics."""
        try:
            # Get current equity
            current_equity = self.equity_curve[-1] if self.equity_curve else self.config.get('bot', {}).get('start_capital', 10000)
            
            # Get statistics
            win_rate = await self.get_win_rate(20)
            sharpe = await self.get_sharpe_ratio()
            max_dd = await self.get_max_drawdown()
            
            # Print arena-style stats
            logger.info("🏟️  ARENA STATS:")
            logger.info(f"   Total Value: ${current_equity:,.2f}")
            logger.info(f"   Win Rate: {win_rate:.1f}%")
            logger.info(f"   Sharpe: {sharpe:.2f}")
            logger.info(f"   Max DD: {max_dd:.1f}%")
            
        except Exception as e:
            logger.error(f"Error printing arena stats: {e}")
    
    async def get_equity_curve(self) -> List[float]:
        """
        Get current equity curve.
        
        Returns:
            List of equity values
        """
        return self.equity_curve.copy()
    
    async def get_total_value(self) -> float:
        """
        Get current total portfolio value.
        
        Returns:
            Total portfolio value
        """
        try:
            if self.equity_curve:
                return self.equity_curve[-1]
            else:
                return self.config.get('bot', {}).get('start_capital', 10000)
        except Exception as e:
            logger.error(f"Error getting total value: {e}")
            return 0.0
    
    async def get_active_positions(self) -> List[Dict[str, Any]]:
        """
        Get active positions (placeholder - would integrate with WebSocket).
        
        Returns:
            List of active position dictionaries
        """
        try:
            # This would integrate with WebSocket to get real-time positions
            # For now, return empty list
            return []
        except Exception as e:
            logger.error(f"Error getting active positions: {e}")
            return []
    
    async def reset_equity_curve(self) -> None:
        """Reset equity curve to initial capital."""
        initial_capital = self.config.get('bot', {}).get('start_capital', 10000)
        self.equity_curve = [initial_capital]
        logger.info(f"🔄 Equity curve reset to ${initial_capital:,.2f}")
