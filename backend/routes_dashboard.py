"""
Dashboard API - Lightweight status dashboard for PesoEcho.
Provides visual overview of system status, reasoning, and performance.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from typing import Dict, Any
import logging

from backend.system.peso_mind import peso_mind
from backend.agents.reasoning_engine import reasoning_engine
from backend.agents.trade_kernel import trade_kernel
from backend.agents.learning_loop import learning_loop

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard() -> HTMLResponse:
    """Get the main dashboard HTML."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PesoEcho Dashboard</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f7;
            color: #1d1d1f;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #00CFFF;
            margin: 0;
            font-size: 2.5rem;
            font-weight: 700;
        }
        .header p {
            color: #86868b;
            margin: 10px 0 0 0;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            border: 1px solid #e5e5e7;
        }
        .card h3 {
            margin: 0 0 15px 0;
            color: #1d1d1f;
            font-size: 1.2rem;
            font-weight: 600;
        }
        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
        }
        .status.running { background: #d4edda; color: #155724; }
        .status.stopped { background: #f8d7da; color: #721c24; }
        .status.degraded { background: #fff3cd; color: #856404; }
        .metric {
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
        }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #86868b; }
        .metric-value { font-weight: 600; }
        .button {
            background: #00CFFF;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
            margin: 5px;
            text-decoration: none;
            display: inline-block;
        }
        .button:hover { background: #00b8e6; }
        .button.secondary {
            background: #86868b;
            color: white;
        }
        .button.secondary:hover { background: #6c6c70; }
        .actions {
            text-align: center;
            margin: 20px 0;
        }
        .log-entry {
            background: #f8f9fa;
            border-radius: 6px;
            padding: 12px;
            margin: 8px 0;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.85rem;
        }
        .timestamp { color: #86868b; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 PesoEcho Dashboard</h1>
            <p>AI Trading System Status & Performance</p>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>🔗 Connection Status</h3>
                <div class="metric">
                    <span class="metric-label">WebSocket</span>
                    <span class="metric-value" id="ws-status">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Data Health</span>
                    <span class="metric-value" id="data-health">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">REST Fallback</span>
                    <span class="metric-value" id="rest-status">Loading...</span>
                </div>
            </div>
            
            <div class="card">
                <h3>🧠 Mind Status</h3>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value" id="mind-status">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Mode</span>
                    <span class="metric-value" id="mind-mode">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Cycle Count</span>
                    <span class="metric-value" id="cycle-count">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Last Cycle</span>
                    <span class="metric-value" id="last-cycle">Loading...</span>
                </div>
            </div>
            
            <div class="card">
                <h3>📊 Performance</h3>
                <div class="metric">
                    <span class="metric-label">Performance Score</span>
                    <span class="metric-value" id="performance-score">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Trend</span>
                    <span class="metric-value" id="performance-trend">Loading...</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Reflections</span>
                    <span class="metric-value" id="reflection-count">Loading...</span>
                </div>
            </div>
            
            <div class="card">
                <h3>💰 Positions</h3>
                <div id="positions-list">Loading...</div>
            </div>
        </div>
        
        <div class="actions">
            <a href="/ops/mind-status" class="button">Refresh Status</a>
            <a href="/ops/reason" class="button secondary">Trigger Reasoning</a>
            <a href="/ops/decide" class="button secondary">Make Decision</a>
            <a href="/ops/reflect" class="button secondary">Run Reflection</a>
        </div>
        
        <div class="card">
            <h3>📝 Recent Activity</h3>
            <div id="recent-activity">Loading...</div>
        </div>
    </div>
    
    <script>
        async function loadDashboard() {
            try {
                // Load mind status
                const mindResponse = await fetch('/ops/mind-status');
                const mindData = await mindResponse.json();
                
                // Update mind status
                document.getElementById('mind-status').textContent = mindData.mind.running ? 'Running' : 'Stopped';
                document.getElementById('mind-mode').textContent = mindData.mind.mode;
                document.getElementById('cycle-count').textContent = mindData.mind.cycle_count;
                document.getElementById('last-cycle').textContent = mindData.mind.last_cycle ? 
                    new Date(mindData.mind.last_cycle).toLocaleTimeString() : 'Never';
                
                // Update performance
                document.getElementById('performance-score').textContent = 
                    mindData.performance.avg_performance_score.toFixed(2);
                document.getElementById('performance-trend').textContent = mindData.performance.trend;
                document.getElementById('reflection-count').textContent = mindData.performance.total_reflections;
                
                // Update positions
                const positionsList = document.getElementById('positions-list');
                if (Object.keys(mindData.positions).length === 0) {
                    positionsList.innerHTML = '<div class="metric"><span class="metric-label">No positions</span></div>';
                } else {
                    positionsList.innerHTML = Object.entries(mindData.positions)
                        .map(([symbol, size]) => 
                            `<div class="metric"><span class="metric-label">${symbol}</span><span class="metric-value">${size.toFixed(2)}</span></div>`
                        ).join('');
                }
                
                // Load connection status
                try {
                    const wsResponse = await fetch('/ops/ws');
                    const wsData = await wsResponse.json();
                    document.getElementById('ws-status').textContent = wsData.connected ? 'Connected' : 'Disconnected';
                } catch (e) {
                    document.getElementById('ws-status').textContent = 'Error';
                }
                
                try {
                    const healthResponse = await fetch('/ops/data-health');
                    const healthData = await healthResponse.json();
                    document.getElementById('data-health').textContent = healthData.status;
                    document.getElementById('rest-status').textContent = healthData.rest_meta_ok ? 'Active' : 'Inactive';
                } catch (e) {
                    document.getElementById('data-health').textContent = 'Error';
                    document.getElementById('rest-status').textContent = 'Error';
                }
                
            } catch (error) {
                console.error('Failed to load dashboard:', error);
            }
        }
        
        // Load dashboard on page load
        loadDashboard();
        
        // Auto-refresh every 30 seconds
        setInterval(loadDashboard, 30000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

@router.get("/dashboard/api/status")
async def get_dashboard_data() -> Dict[str, Any]:
    """Get dashboard data as JSON."""
    try:
        # Get mind status
        mind_status = peso_mind.get_status()
        positions = peso_mind.get_positions()
        performance = peso_mind.get_performance_summary()
        
        return {
            "mind": mind_status,
            "positions": positions,
            "performance": performance,
            "timestamp": "2025-01-25T13:00:00Z"
        }
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {e}")
        return {
            "error": str(e),
            "timestamp": "2025-01-25T13:00:00Z"
        }
