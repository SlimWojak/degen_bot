"""
Database schema bootstrap and initialization.
Creates SQLite tables if missing (idempotent).
"""

import sqlite3
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

def init_db(db_path: str = "data/pesoecho.db") -> bool:
    """
    Initialize database with required tables.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        tables = [
            {
                "name": "deepseek_thoughts",
                "schema": """
                    CREATE TABLE IF NOT EXISTS deepseek_thoughts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        symbol TEXT,
                        action TEXT,
                        reason TEXT,
                        raw_json TEXT
                    )
                """
            },
            {
                "name": "agent_decisions", 
                "schema": """
                    CREATE TABLE IF NOT EXISTS agent_decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        intent_id TEXT UNIQUE,
                        symbol TEXT,
                        action TEXT,
                        notional REAL,
                        mode TEXT,
                        result TEXT,
                        latency_ms INTEGER,
                        meta TEXT
                    )
                """
            },
            {
                "name": "sim_trades",
                "schema": """
                    CREATE TABLE IF NOT EXISTS sim_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        symbol TEXT,
                        side TEXT,
                        qty REAL,
                        fill_px REAL,
                        fee REAL,
                        slippage_bps REAL,
                        pnl_after REAL
                    )
                """
            }
        ]
        
        for table in tables:
            cursor.execute(table["schema"])
            logger.info(f"Ensured table {table['name']} exists")
        
        # Create indexes for better performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_deepseek_thoughts_ts ON deepseek_thoughts(ts)",
            "CREATE INDEX IF NOT EXISTS idx_agent_decisions_intent_id ON agent_decisions(intent_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_decisions_ts ON agent_decisions(ts)",
            "CREATE INDEX IF NOT EXISTS idx_sim_trades_ts ON sim_trades(ts)",
            "CREATE INDEX IF NOT EXISTS idx_sim_trades_symbol ON sim_trades(symbol)"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        conn.commit()
        conn.close()
        
        logger.info(f"Database initialized successfully: {db_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False

def get_db_path() -> str:
    """Get the database path from environment or default."""
    return os.getenv("DB_PATH", "data/pesoecho.db")

def check_db_health() -> dict:
    """Check database health and return status."""
    try:
        db_path = get_db_path()
        if not os.path.exists(db_path):
            return {"status": "missing", "path": db_path}
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = ["deepseek_thoughts", "agent_decisions", "sim_trades"]
        missing_tables = [t for t in expected_tables if t not in tables]
        
        conn.close()
        
        if missing_tables:
            return {"status": "incomplete", "missing_tables": missing_tables}
        else:
            return {"status": "healthy", "tables": tables}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}
