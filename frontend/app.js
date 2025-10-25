// Professional Trading Cockpit - Real-time Dashboard
class TradingDashboard {
    constructor() {
        this.ws = null;
        this.chart = null;
        this.isConnected = false;
        this.updateInterval = null;
        this.dataPoller = null;
        this.selectedSymbols = ['ETH']; // Default selected symbols
        this.symbolData = {}; // Cache data per symbol
        this.marketMicroData = {}; // Cache market microstructure data
        
        this.init();
    }
    
    init() {
        // Wait for DOM to be fully loaded
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.initializeAfterDOM();
            });
        } else {
            this.initializeAfterDOM();
        }
    }
    
    initializeAfterDOM() {
        console.log('📄 DOM is ready, initializing dashboard...');
        
        this.setupChart();
        this.connectWebSocket();
        this.setupEventListeners();
        this.setupControlBar();
        this.setupSymbolPicker();
        this.startPeriodicUpdates();
        this.startDataPolling();
        this.startAILogsPolling();
        this.startMarketMicroPolling();
        
        // Load initial data
        this.loadInitialData();
        
        // Update status badges immediately
        this.updateStatusBadges();
    }
    
    // Custom SVG Chart Setup - TradingView Style
    setupChart() {
        console.log('🔧 Setting up Custom SVG Chart...');
        
        const chartContainer = document.querySelector('.chart-container');
        if (!chartContainer) {
            console.error('❌ Chart container not found!');
            return;
        }
        
        console.log('✅ Chart container found:', chartContainer);
        
        // Clear any existing content
        chartContainer.innerHTML = '';
        
        // Create SVG element
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        svg.setAttribute('viewBox', '0 0 800 400');
        svg.style.background = '#1a1d24';
        svg.style.borderRadius = '8px';
        
        // Add to container
        chartContainer.appendChild(svg);
        
        // Store reference
        this.chart = svg;
        this.chartContainer = chartContainer;
        
        // Initialize with sample data
        this.updateChartWithData([
            { timestamp: '2025-10-24T10:00:00', value: 10000 },
            { timestamp: '2025-10-24T11:00:00', value: 10100 },
            { timestamp: '2025-10-24T12:00:00', value: 10200 },
            { timestamp: '2025-10-24T13:00:00', value: 10150 },
            { timestamp: '2025-10-24T14:00:00', value: 10300 }
        ]);
        
        console.log('✅ Custom SVG Chart initialized successfully');
    }
    
    
    // REAL WebSocket Connection with Validation
    connectWebSocket() {
        console.log('🔌 Attempting WebSocket connection to ws://localhost:8000/ws');
        
        try {
            this.ws = new WebSocket('ws://localhost:8000/ws');
            
            this.ws.onopen = (event) => {
                console.log('✅ WebSocket REALLY connected to backend');
                this.isConnected = true;
                this.updateConnectionStatus('🟢 Connected');
                
                // Request subscription to real data channels
                this.ws.send(JSON.stringify({
                    type: 'subscribe',
                    channels: ['metrics', 'equity', 'positions', 'trades', 'reasoning']
                }));
                console.log('📡 Subscribed to real-time data channels');
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const realData = JSON.parse(event.data);
                    console.log('📡 Real WebSocket data received:', realData);
                    
                    // Update dashboard with real WebSocket data
                    this.updateDashboard(realData);
                    this.updateLastUpdateTime();
                } catch (error) {
                    console.error('❌ Failed to parse WebSocket data:', error);
                }
            };
            
            this.ws.onclose = (event) => {
                console.log('❌ WebSocket disconnected:', event.code, event.reason);
                this.isConnected = false;
                this.updateConnectionStatus('🔴 Disconnected');
                
                // Attempt to reconnect after 3 seconds
                setTimeout(() => {
                    console.log('🔄 Attempting WebSocket reconnection...');
                    this.connectWebSocket();
                }, 3000);
            };
            
            this.ws.onerror = (error) => {
                console.error('❌ WebSocket error:', error);
                this.updateConnectionStatus('🔴 Error');
            };
        } catch (error) {
            console.error('❌ Failed to create WebSocket:', error);
            this.updateConnectionStatus('🔴 Failed');
        }
    }
    
    // Event Listeners
    setupEventListeners() {
        // Time period buttons
        document.querySelectorAll('.time-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.updateChartPeriod(e.target.dataset.period);
            });
        });
    }
    
    // Setup Control Bar
    setupControlBar() {
        console.log('🎛️ Setting up control bar...');
        
        // Kill switch toggle
        const killSwitchToggle = document.getElementById('kill-switch-toggle');
        if (killSwitchToggle) {
            killSwitchToggle.addEventListener('change', (e) => {
                this.toggleKillSwitch(e.target.checked);
            });
        }
        
        // Trade buttons
        const buyBtn = document.getElementById('buy-btn');
        const sellBtn = document.getElementById('sell-btn');
        const aiBtn = document.getElementById('ai-btn');
        
        if (buyBtn) {
            buyBtn.addEventListener('click', () => this.placeOrder('buy'));
        }
        
        if (sellBtn) {
            sellBtn.addEventListener('click', () => this.placeOrder('sell'));
        }
        
        if (aiBtn) {
            aiBtn.addEventListener('click', () => this.letAIDecide());
        }
        
        // Load initial kill switch state
        this.loadKillSwitchState();
        
        console.log('✅ Control bar setup complete');
    }
    
    // Setup Symbol Picker
    setupSymbolPicker() {
        console.log('🎯 Setting up symbol picker...');
        
        const symbolSelect = document.getElementById('symbol-select');
        if (symbolSelect) {
            // Load initial selected symbols
            this.selectedSymbols = Array.from(symbolSelect.selectedOptions).map(option => option.value);
            
            // Listen for changes
            symbolSelect.addEventListener('change', (e) => {
                this.selectedSymbols = Array.from(e.target.selectedOptions).map(option => option.value);
                console.log('📊 Selected symbols:', this.selectedSymbols);
                
                // Update UI with new symbol selection
                this.updateSymbolDisplay();
                
                // Refresh data for selected symbols
                this.refreshSymbolData();
            });
        }
        
        console.log('✅ Symbol picker setup complete');
    }
    
    // Load kill switch state
    async loadKillSwitchState() {
        try {
            const response = await fetch('/ai/kill_switch');
            const data = await response.json();
            const killSwitchToggle = document.getElementById('kill-switch-toggle');
            if (killSwitchToggle) {
                killSwitchToggle.checked = data.enabled;
            }
            this.updateControlBarState(data.enabled);
        } catch (error) {
            console.error('❌ Failed to load kill switch state:', error);
        }
    }
    
    // Toggle kill switch
    async toggleKillSwitch(enabled) {
        try {
            const response = await fetch('/ai/kill_switch', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ enabled })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.updateControlBarState(data.enabled);
                this.showToast(enabled ? '🟢 Kill switch ON' : '🔴 Kill switch OFF', 'info');
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (error) {
            console.error('❌ Failed to toggle kill switch:', error);
            this.showToast('❌ Failed to toggle kill switch', 'error');
            // Revert toggle state
            const killSwitchToggle = document.getElementById('kill-switch-toggle');
            if (killSwitchToggle) {
                killSwitchToggle.checked = !enabled;
            }
        }
    }
    
    // Update control bar state
    updateControlBarState(killSwitchEnabled) {
        const buyBtn = document.getElementById('buy-btn');
        const sellBtn = document.getElementById('sell-btn');
        const aiBtn = document.getElementById('ai-btn');
        
        const isEnabled = killSwitchEnabled && this.isBotOk();
        
        [buyBtn, sellBtn, aiBtn].forEach(btn => {
            if (btn) {
                btn.disabled = !isEnabled;
            }
        });
    }
    
    // Check if bot is OK
    isBotOk() {
        const botStatus = document.getElementById('bot-status');
        if (botStatus) {
            const statusText = botStatus.textContent.toLowerCase();
            return statusText.includes('ok') || statusText.includes('mock');
        }
        return false;
    }
    
    // Place order
    async placeOrder(side) {
        const button = document.getElementById(`${side}-btn`);
        if (button) {
            button.disabled = true;
            button.textContent = 'Placing...';
        }
        
        try {
            const response = await fetch('/ai/order/limit_ioc', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    symbol: this.selectedSymbols[0] || 'ETH',
                    side: side,
                    notional_usd: 15,
                    reduce_only: false
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.showToast(
                    `✅ ${side.toUpperCase()} order placed! ID: ${data.order_id}, Avg: $${data.avg_px}`,
                    'success'
                );
                // Refresh positions and trades
                this.refreshTradingData();
            } else {
                this.showToast(`❌ Order failed: ${data.detail?.error || 'Unknown error'}`, 'error');
            }
        } catch (error) {
            console.error(`❌ Failed to place ${side} order:`, error);
            this.showToast(`❌ Order failed: ${error.message}`, 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = `${side.charAt(0).toUpperCase() + side.slice(1)} $15 IOC`;
            }
        }
    }
    
    // Let AI decide
    async letAIDecide() {
        const button = document.getElementById('ai-btn');
        if (button) {
            button.disabled = true;
            button.textContent = 'AI Thinking...';
        }
        
        try {
            const response = await fetch('/agent/decide_and_execute', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (response.ok) {
                if (data.status === 'noop') {
                    this.showToast('🤖 AI: No action needed', 'info');
                } else if (data.execution && data.execution.status === 'executed') {
                    const exec = data.execution;
                    this.showToast(
                        `🤖 AI: ${exec.side.toUpperCase()} $${exec.notional_usd} ${exec.symbol} @ $${exec.avg_px || 'N/A'}`,
                        'success'
                    );
                    // Refresh trading data
                    this.refreshTradingData();
                } else if (data.execution && data.execution.status === 'error') {
                    this.showToast(`🤖 AI: Execution failed - ${data.execution.error}`, 'error');
                } else {
                    this.showToast('🤖 AI: Decision made but not executed', 'info');
                }
            } else {
                this.showToast(`🤖 AI: ${data.detail?.error || 'Decision failed'}`, 'error');
            }
        } catch (error) {
            console.error('❌ AI decision failed:', error);
            this.showToast(`🤖 AI: ${error.message}`, 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = 'Let AI Decide';
            }
        }
    }
    
    // Refresh trading data
    async refreshTradingData() {
        try {
            // Trigger manual refresh of positions and trades
            await this.pollAllData();
        } catch (error) {
            console.error('❌ Failed to refresh trading data:', error);
        }
    }
    
    // Show toast notification
    showToast(message, type = 'info') {
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            color: white;
            font-weight: 500;
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
            max-width: 300px;
            word-wrap: break-word;
        `;
        
        // Set background color based on type
        const colors = {
            success: '#00d395',
            error: '#ff6b6b',
            info: '#667eea',
            warning: '#ffa500'
        };
        toast.style.backgroundColor = colors[type] || colors.info;
        
        // Add to DOM
        document.body.appendChild(toast);
        
        // Remove after 3 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }
    
    // Periodic Updates (fallback if WebSocket fails)
    startPeriodicUpdates() {
        this.updateInterval = setInterval(() => {
            if (!this.isConnected) {
                this.fetchDataFromAPI();
            }
            // Always update status badges
            this.updateStatusBadges();
        }, 5000); // Update every 5 seconds as fallback
    }
    
    // Start data polling with 1.5s interval
    startDataPolling() {
        this.dataPoller = new DataPoller();
        this.dataPoller.start(async () => {
            await this.pollAllData();
        }, 1500);
    }
    
    // Poll all data with deduplication
    async pollAllData() {
        try {
            const [metrics, positions, trades, equity, status] = await Promise.all([
                this.dataPoller.withDedupe('metrics', () => this.fetchMetrics()),
                this.dataPoller.withDedupe('positions', () => this.fetchPositions()),
                this.dataPoller.withDedupe('trades', () => this.fetchTrades()),
                this.dataPoller.withDedupe('equity', () => this.fetchEquity()),
                this.dataPoller.withDedupe('status', () => this.fetchStatus())
            ]);
            
            this.updateDashboard({
                metrics,
                positions,
                trades,
                equity,
                status
            });
            
            this.updateStatusBadges(status);
        } catch (error) {
            console.error('❌ Polling error:', error);
        }
    }
    
    // REAL API Data Fetching with Error Handling
    async fetchDataFromAPI() {
        console.log('📡 Fetching real data from backend APIs...');
        
        try {
            const [metrics, equity, positions, trades, reasoning, prices] = await Promise.all([
                this.fetchRealMetrics(),
                this.fetchRealEquity(),
                this.fetchRealPositions(),
                this.fetchRealTrades(),
                this.fetchRealReasoning(),
                this.fetchRealPrices()
            ]);
            
            console.log('✅ Real data fetched:', { metrics, equity, positions, trades, reasoning, prices });
            
            this.updateDashboard({
                metrics,
                equity,
                positions,
                trades,
                reasoning,
                prices
            });
            
            this.updateConnectionStatus('🟢 API Connected');
        } catch (error) {
            console.error('❌ Failed to fetch real data:', error);
            this.updateConnectionStatus('🔴 API Error');
        }
    }
    
    // New API methods using data client
    async fetchMetrics() {
        try {
            const data = await getSummary();
            console.log('📊 Metrics:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch metrics:', error);
            return null;
        }
    }
    
    async fetchEquity() {
        try {
            const data = await getEquity();
            console.log('📈 Equity data:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch equity:', error);
            return [];
        }
    }
    
    async fetchPositions() {
        try {
            const data = await getPositions();
            console.log('💼 Positions:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch positions:', error);
            return [];
        }
    }
    
    async fetchTrades() {
        try {
            const data = await getTrades(50);
            console.log('📋 Trades:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch trades:', error);
            return [];
        }
    }
    
    async fetchStatus() {
        try {
            const data = await getStatus();
            console.log('🔍 Status:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch status:', error);
            return null;
        }
    }
    
    // Legacy methods for backward compatibility
    async fetchRealMetrics() {
        return this.fetchMetrics();
    }
    
    async fetchRealEquity() {
        return this.fetchEquity();
    }
    
    async fetchRealPositions() {
        return this.fetchPositions();
    }
    
    async fetchRealTrades() {
        return this.fetchTrades();
    }
    
    async fetchRealReasoning() {
        try {
            const response = await fetch('/reasoning');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            console.log('🤖 Real reasoning:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch reasoning:', error);
            return [];
        }
    }
    
    async fetchRealPrices() {
        try {
            const response = await fetch('/prices');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            console.log('💰 Real prices:', data);
            return data;
        } catch (error) {
            console.error('❌ Failed to fetch prices:', error);
            return {};
        }
    }
    
    // Load Initial Data
    async loadInitialData() {
        await this.fetchDataFromAPI();
    }
    
    // Update Dashboard with New Data
    updateDashboard(data) {
        if (data.metrics) this.updateMetrics(data.metrics);
        if (data.equity) this.updateChart(data.equity);
        if (data.positions) this.updatePositions(data.positions);
        if (data.trades) this.updateTrades(data.trades);
        if (data.reasoning) this.updateReasoning(data.reasoning);
        if (data.prices) this.updatePrices(data.prices);
        if (data.status) this.updateStatusBadges(data.status);
        
        this.updateLastUpdateTime();
    }
    
    // Update Metrics Panel with Real Data
    updateMetrics(metrics) {
        if (!metrics) {
            console.warn('⚠️ No metrics data provided');
            return;
        }
        
        console.log('📊 Updating metrics with real data:', metrics);
        
        // Check for insufficient data
        if (isInsufficientData(metrics)) {
            this.showInsufficientData('metrics');
            return;
        }
        
        // Add stale badge if data is stale
        if (isStaleData(metrics)) {
            this.addStaleBadge('metrics');
        }
        
        // Update portfolio value with real data
        const portfolioValue = metrics.total_value || 0;
        document.getElementById('portfolio-value').textContent = `$${portfolioValue.toLocaleString()}`;
        
        // Calculate daily P&L from real data
        const dailyPnl = metrics.daily_pnl || 0;
        const dailyPnlPct = metrics.daily_pnl_pct || 0;
        document.getElementById('daily-pnl').textContent = `$${dailyPnl.toFixed(2)} (${dailyPnlPct.toFixed(1)}%)`;
        
        // Update all metrics with real values
        document.getElementById('win-rate').textContent = `${(metrics.win_rate * 100 || 0).toFixed(1)}%`;
        document.getElementById('sharpe-ratio').textContent = metrics.sharpe?.toFixed(1) || '0';
        document.getElementById('max-drawdown').textContent = `${metrics.max_dd || 0}%`;
        document.getElementById('total-trades').textContent = metrics.trades || '0';
        document.getElementById('active-trades').textContent = metrics.active_trades || '0';
        document.getElementById('daily-pnl-metric').textContent = `${dailyPnlPct.toFixed(1)}%`;
        
        console.log('✅ Metrics updated with real data');
    }
    
    // Helper methods for data state handling
    showInsufficientData(widgetType) {
        const widget = document.querySelector(`[data-widget="${widgetType}"]`);
        if (widget) {
            const pill = document.createElement('div');
            pill.className = 'insufficient-data-pill';
            pill.textContent = 'Insufficient data';
            pill.style.cssText = 'background: #ff6b6b; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px; margin: 4px;';
            widget.appendChild(pill);
        }
    }
    
    addStaleBadge(widgetType) {
        const widget = document.querySelector(`[data-widget="${widgetType}"]`);
        if (widget) {
            // Remove existing stale badge
            const existingBadge = widget.querySelector('.stale-badge');
            if (existingBadge) existingBadge.remove();
            
            const badge = document.createElement('div');
            badge.className = 'stale-badge';
            badge.textContent = 'stale';
            badge.style.cssText = 'background: #ffa500; color: white; padding: 2px 6px; border-radius: 8px; font-size: 10px; position: absolute; top: 4px; right: 4px;';
            widget.style.position = 'relative';
            widget.appendChild(badge);
        }
    }
    
    // Update Chart with Real Data - Custom SVG
    updateChart(equityData) {
        if (!this.chart) {
            console.error('❌ Chart not initialized');
            return;
        }
        
        if (!equityData || equityData.length === 0) {
            console.warn('⚠️ No equity data provided');
            this.showNoHistoryMessage();
            return;
        }
        
        // Add stale badge if data is stale
        if (isStaleData(equityData)) {
            this.addStaleBadge('chart');
        }
        
        console.log('📈 Updating custom SVG chart with real equity data:', equityData.length, 'points');
        this.updateChartWithData(equityData);
    }
    
    showNoHistoryMessage() {
        const chartContainer = document.querySelector('.chart-container');
        if (chartContainer) {
            chartContainer.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #666; font-size: 14px;">
                    📈 No history yet
                </div>
            `;
        }
    }
    
    // Custom SVG Chart Rendering
    updateChartWithData(data) {
        if (!this.chart || !data || data.length === 0) {
            console.warn('⚠️ Cannot update chart - no data or chart not initialized');
            return;
        }
        
        console.log('🎨 Rendering custom SVG chart with', data.length, 'data points');
        
        // Clear existing content
        this.chart.innerHTML = '';
        
        // Chart dimensions
        const width = 800;
        const height = 400;
        const padding = 40;
        const chartWidth = width - (padding * 2);
        const chartHeight = height - (padding * 2);
        
        // Find min/max values
        const values = data.map(d => d.value);
        const minValue = Math.min(...values);
        const maxValue = Math.max(...values);
        const valueRange = maxValue - minValue;
        
        // Add some padding to the range
        const paddedMin = minValue - (valueRange * 0.1);
        const paddedMax = maxValue + (valueRange * 0.1);
        const paddedRange = paddedMax - paddedMin;
        
        // Helper function to convert value to Y coordinate
        const valueToY = (value) => {
            return height - padding - ((value - paddedMin) / paddedRange) * chartHeight;
        };
        
        // Helper function to convert index to X coordinate
        const indexToX = (index) => {
            return padding + (index / (data.length - 1)) * chartWidth;
        };
        
        // Create grid lines
        const gridGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        gridGroup.setAttribute('stroke', '#2d3748');
        gridGroup.setAttribute('stroke-width', '1');
        gridGroup.setAttribute('opacity', '0.5');
        
        // Horizontal grid lines
        for (let i = 0; i <= 4; i++) {
            const y = padding + (i / 4) * chartHeight;
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', padding);
            line.setAttribute('y1', y);
            line.setAttribute('x2', width - padding);
            line.setAttribute('y2', y);
            gridGroup.appendChild(line);
        }
        
        // Vertical grid lines
        for (let i = 0; i <= 4; i++) {
            const x = padding + (i / 4) * chartWidth;
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', x);
            line.setAttribute('y1', padding);
            line.setAttribute('x2', x);
            line.setAttribute('y2', height - padding);
            gridGroup.appendChild(line);
        }
        
        this.chart.appendChild(gridGroup);
        
        // Create area path
        let areaPath = `M ${indexToX(0)} ${valueToY(data[0].value)}`;
        for (let i = 1; i < data.length; i++) {
            areaPath += ` L ${indexToX(i)} ${valueToY(data[i].value)}`;
        }
        areaPath += ` L ${indexToX(data.length - 1)} ${height - padding}`;
        areaPath += ` L ${indexToX(0)} ${height - padding} Z`;
        
        const area = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        area.setAttribute('d', areaPath);
        area.setAttribute('fill', 'rgba(0, 211, 149, 0.1)');
        this.chart.appendChild(area);
        
        // Create line path
        let linePath = `M ${indexToX(0)} ${valueToY(data[0].value)}`;
        for (let i = 1; i < data.length; i++) {
            linePath += ` L ${indexToX(i)} ${valueToY(data[i].value)}`;
        }
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        line.setAttribute('d', linePath);
        line.setAttribute('stroke', '#00d395');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('fill', 'none');
        this.chart.appendChild(line);
        
        // Add data points
        data.forEach((point, index) => {
            const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circle.setAttribute('cx', indexToX(index));
            circle.setAttribute('cy', valueToY(point.value));
            circle.setAttribute('r', '3');
            circle.setAttribute('fill', '#00d395');
            circle.setAttribute('opacity', '0.8');
            
            // Add hover effect
            circle.addEventListener('mouseenter', () => {
                circle.setAttribute('r', '6');
                circle.setAttribute('fill', '#00CFFF');
            });
            circle.addEventListener('mouseleave', () => {
                circle.setAttribute('r', '3');
                circle.setAttribute('fill', '#00d395');
            });
            
            this.chart.appendChild(circle);
        });
        
        // Add Y-axis labels
        const labelGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        labelGroup.setAttribute('fill', '#8892b0');
        labelGroup.setAttribute('font-size', '11');
        labelGroup.setAttribute('font-family', 'Arial, sans-serif');
        
        for (let i = 0; i <= 4; i++) {
            const value = paddedMin + (i / 4) * paddedRange;
            const y = padding + (i / 4) * chartHeight;
            
            const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            text.setAttribute('x', padding - 10);
            text.setAttribute('y', y + 4);
            text.setAttribute('text-anchor', 'end');
            text.textContent = '$' + Math.round(value).toLocaleString();
            labelGroup.appendChild(text);
        }
        
        this.chart.appendChild(labelGroup);
        
        console.log('✅ Custom SVG chart rendered successfully');
    }
    
    // Update Positions Table with Real Data
    updatePositions(positions) {
        if (!positions || positions.length === 0) {
            console.warn('⚠️ No positions data provided');
            this.showNoPositionsMessage();
            return;
        }
        
        // Add stale badge if data is stale
        if (isStaleData(positions)) {
            this.addStaleBadge('positions');
        }
        
        console.log('💼 Updating positions with real data:', positions);
        
        const tbody = document.getElementById('positions-tbody');
        tbody.innerHTML = '';
        
        positions.forEach(position => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${position.coin}</td>
                <td><span class="side ${position.side.toLowerCase()}">${position.side.toUpperCase()}</span></td>
                <td>${position.qty}</td>
                <td>$${position.entry}</td>
                <td>$${position.current}</td>
                <td class="${position.pnl >= 0 ? 'positive' : 'negative'}">${position.pnl >= 0 ? '+' : ''}$${position.pnl.toFixed(2)}</td>
            `;
            tbody.appendChild(row);
        });
        
        console.log('✅ Positions updated with', positions.length, 'real positions');
    }
    
    showNoPositionsMessage() {
        const tbody = document.getElementById('positions-tbody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; color: #666; padding: 20px;">
                        📊 No open positions
                    </td>
                </tr>
            `;
        }
    }
    
    // Update Trades Table
    updateTrades(trades) {
        const tbody = document.getElementById('trades-tbody');
        tbody.innerHTML = '';
        
        if (!trades || trades.length === 0) {
            this.showNoTradesMessage();
            return;
        }
        
        // Add stale badge if data is stale
        if (isStaleData(trades)) {
            this.addStaleBadge('trades');
        }
        
        trades.forEach(trade => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${trade.time}</td>
                <td>${trade.coin}</td>
                <td><span class="side ${trade.side.toLowerCase()}">${trade.side.toUpperCase()}</span></td>
                <td>${trade.qty}</td>
                <td>$${trade.entry}</td>
                <td>$${trade.exit}</td>
                <td class="${trade.pnl >= 0 ? 'positive' : 'negative'}">${trade.pnl >= 0 ? '+' : ''}$${trade.pnl}</td>
            `;
            tbody.appendChild(row);
        });
    }
    
    showNoTradesMessage() {
        const tbody = document.getElementById('trades-tbody');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; color: #666; padding: 20px;">
                        📋 No completed trades
                    </td>
                </tr>
            `;
        }
    }
    
    // Update Reasoning Cards
    updateReasoning(reasoning) {
        const container = document.getElementById('reasoning-cards');
        container.innerHTML = '';
        
        reasoning.forEach(item => {
            const card = document.createElement('div');
            card.className = 'reasoning-card';
            card.innerHTML = `
                <div class="card-header">
                    <span class="ai-icon">🤖</span>
                    <span class="asset">${item.asset} Analysis</span>
                    <span class="timestamp">${item.time}</span>
                </div>
                <div class="card-content">
                    <p>${item.signals} - ${item.bias}</p>
                    <div class="action-info">
                        <span class="action">Action: ${item.recommendation}</span>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    }
    
    // Update Prices (if needed)
    updatePrices(prices) {
        // Could update live price ticker if implemented
        console.log('Live prices:', prices);
    }
    
    // Update Chart Period
    updateChartPeriod(period) {
        // This would filter chart data based on selected period
        console.log('Chart period changed to:', period);
        // Implementation would depend on backend API support
    }
    
    // Update Connection Status with Visual Indicators
    updateConnectionStatus(status) {
        const wsStatus = document.getElementById('ws-status');
        const apiStatus = document.getElementById('api-status');
        const dbStatus = document.getElementById('db-status');
        
        if (status.includes('🟢')) {
            wsStatus.textContent = status;
            wsStatus.className = 'status-connected';
            apiStatus.textContent = '🟢 Healthy';
            dbStatus.textContent = '🟢 Synced';
        } else if (status.includes('🔴')) {
            wsStatus.textContent = status;
            wsStatus.className = 'status-disconnected';
            apiStatus.textContent = '🔴 Error';
            dbStatus.textContent = '🔴 Error';
        }
        
        console.log('🔗 Connection status updated:', status);
    }
    
    // Update status badges using /status endpoint
    async updateStatusBadges(statusData = null) {
        try {
            if (!statusData) {
                statusData = await getStatus();
            }
            
            // Update status lights with new data structure
            this.updateStatusLight('bot-status', statusData.bot);
            this.updateStatusLight('market-status', statusData.market);
            this.updateStatusLight('api-status', statusData.api);
            this.updateStatusLight('db-status', statusData.db);
            this.updateStatusLight('ws-status', statusData.ws);
            
            // Update control bar state based on bot status
            this.updateControlBarState(this.isBotOk());
            
            console.log('📊 Status badges updated:', statusData);
            
        } catch (error) {
            console.error('❌ Failed to update status badges:', error);
            this.updateStatusLight('bot-status', 'error');
            this.updateStatusLight('market-status', 'error');
            this.updateStatusLight('api-status', 'error');
            this.updateStatusLight('db-status', 'error');
            this.updateStatusLight('ws-status', 'error');
        }
    }
    
    updateStatusLight(elementId, status) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const statusMap = {
            'ok': '🟢 OK',
            'healthy': '🟢 HEALTHY',
            'synced': '🟢 SYNCED',
            'connected': '🟢 CONNECTED',
            'mock': '🟡 MOCK',
            'stale': '🟡 STALE',
            'disconnected': '🔴 DISCONNECTED',
            'error': '🔴 ERROR',
            'unknown': '⚪ UNKNOWN'
        };
        
        element.textContent = statusMap[status] || `⚪ ${status?.toUpperCase() || 'UNKNOWN'}`;
    }
    
    // Update Last Update Time with Real-time Validation
    updateLastUpdateTime() {
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        document.getElementById('last-update').textContent = `Last Update: ${timeString}`;
        
        // Add visual indicator of data freshness
        const lastUpdateElement = document.getElementById('last-update');
        lastUpdateElement.style.color = '#00d395';
        lastUpdateElement.style.fontWeight = '500';
        
        // Reset color after 2 seconds
        setTimeout(() => {
            lastUpdateElement.style.color = '#8892b0';
            lastUpdateElement.style.fontWeight = 'normal';
        }, 2000);
        
        console.log('⏰ Data freshness updated:', timeString);
    }
    
    // Real Data Validation and Debugging
    validateRealData(data) {
        console.log('🔍 Validating real data:', data);
        
        if (data.metrics) {
            console.log('✅ Metrics data valid:', Object.keys(data.metrics));
        }
        if (data.equity) {
            console.log('✅ Equity data valid:', data.equity.length, 'points');
        }
        if (data.positions) {
            console.log('✅ Positions data valid:', data.positions.length, 'positions');
        }
        if (data.trades) {
            console.log('✅ Trades data valid:', data.trades.length, 'trades');
        }
        if (data.reasoning) {
            console.log('✅ Reasoning data valid:', data.reasoning.length, 'insights');
        }
    }
    
    // Start AI logs polling
    startAILogsPolling() {
        this.aiLogsPoller = new DataPoller();
        this.aiLogsPoller.start(async () => {
            await this.pollAILogs();
        }, 1500);
    }
    
    // Poll AI logs
    async pollAILogs() {
        try {
            const logs = await this.dataPoller.withDedupe('ai-logs', () => this.fetchAILogs());
            this.updateAILogs(logs);
        } catch (error) {
            console.error('❌ AI logs polling error:', error);
        }
    }
    
    // Fetch AI logs
    async fetchAILogs() {
        try {
            const response = await fetch('/agent/logs?limit=50');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const logs = await response.json();
            console.log('🤖 AI logs:', logs);
            return logs;
        } catch (error) {
            console.error('❌ Failed to fetch AI logs:', error);
            return [];
        }
    }
    
    // Update AI logs table
    updateAILogs(logs) {
        const tbody = document.getElementById('ai-logs-tbody');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        if (!logs || logs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; color: #666; padding: 20px;">
                        🤖 No AI decisions yet
                    </td>
                </tr>
            `;
            return;
        }
        
        logs.forEach(log => {
            const row = document.createElement('tr');
            
            // Format time
            const time = new Date(log.decided_at).toLocaleTimeString();
            
            // Format action
            const action = log.action || 'unknown';
            
            // Format symbol/side
            let symbolSide = '-';
            if (log.payload && log.payload.action === 'order') {
                symbolSide = `${log.payload.symbol}/${log.payload.side}`;
            }
            
            // Format notional
            let notional = '-';
            if (log.payload && log.payload.notional_usd) {
                notional = `$${log.payload.notional_usd}`;
            }
            
            // Format executed
            const executed = log.executed ? '✅ Yes' : '❌ No';
            
            // Format result
            let result = '-';
            if (log.result) {
                if (log.result.status === 'executed') {
                    result = `✅ ${log.result.symbol} @ $${log.result.avg_px || 'N/A'}`;
                } else if (log.result.status === 'error') {
                    result = `❌ ${log.result.error}`;
                } else if (log.result.blocked) {
                    result = `🚫 Blocked: ${log.result.reasons?.join(', ') || 'Unknown'}`;
                }
            }
            
            row.innerHTML = `
                <td>${time}</td>
                <td>${action}</td>
                <td>${symbolSide}</td>
                <td>${notional}</td>
                <td>${executed}</td>
                <td>${result}</td>
            `;
            tbody.appendChild(row);
        });
    }

    // Update symbol display
    updateSymbolDisplay() {
        // Update trade button text to show current symbol
        const buyBtn = document.getElementById('buy-btn');
        const sellBtn = document.getElementById('sell-btn');
        
        if (buyBtn && sellBtn) {
            const primarySymbol = this.selectedSymbols[0] || 'ETH';
            buyBtn.textContent = `Buy $15 ${primarySymbol}`;
            sellBtn.textContent = `Sell $15 ${primarySymbol}`;
        }
    }
    
    // Refresh symbol data
    async refreshSymbolData() {
        console.log('🔄 Refreshing data for symbols:', this.selectedSymbols);
        
        // Fetch data for each selected symbol
        for (const symbol of this.selectedSymbols) {
            try {
                const [positions, trades] = await Promise.all([
                    this.dataPoller.withDedupe(`positions-${symbol}`, () => 
                        fetch(`/positions?symbol=${symbol}`).then(r => r.json())
                    ),
                    this.dataPoller.withDedupe(`trades-${symbol}`, () => 
                        fetch(`/trades?symbol=${symbol}`).then(r => r.json())
                    )
                ]);
                
                // Cache the data
                this.symbolData[symbol] = { positions, trades };
                
                console.log(`📊 Data cached for ${symbol}:`, { positions: positions.length, trades: trades.length });
            } catch (error) {
                console.error(`❌ Failed to fetch data for ${symbol}:`, error);
            }
        }
        
        // Update the UI with aggregated data
        this.updateSymbolDataDisplay();
    }
    
    // Update symbol data display
    updateSymbolDataDisplay() {
        // Aggregate positions from all selected symbols
        const allPositions = [];
        const allTrades = [];
        
        for (const symbol of this.selectedSymbols) {
            if (this.symbolData[symbol]) {
                allPositions.push(...this.symbolData[symbol].positions);
                allTrades.push(...this.symbolData[symbol].trades);
            }
        }
        
        // Update positions and trades tables
        this.updatePositions(allPositions);
        this.updateTrades(allTrades);
    }
    
    // Start market microstructure polling
    startMarketMicroPolling() {
        console.log('📊 Starting market micro polling...');
        
        // Poll every 1.5s for market micro data
        setInterval(async () => {
            await this.pollMarketMicro();
        }, 1500);
        
        // Initial poll
        this.pollMarketMicro();
    }
    
    // Poll market microstructure data
    async pollMarketMicro() {
        const primarySymbol = this.selectedSymbols[0] || 'ETH';
        
        try {
            const response = await fetch(`/market/snapshot?symbol=${primarySymbol}`);
            const data = await response.json();
            
            if (response.ok && !data.meta?.insufficient) {
                this.marketMicroData[primarySymbol] = data;
                this.updateMarketMicroDisplay(primarySymbol);
            } else {
                // Clear display if no data
                this.clearMarketMicroDisplay();
            }
        } catch (error) {
            console.error('❌ Failed to fetch market micro data:', error);
            this.clearMarketMicroDisplay();
        }
    }
    
    // Update market micro display
    updateMarketMicroDisplay(symbol) {
        const data = this.marketMicroData[symbol];
        if (!data || !data.micro) {
            this.clearMarketMicroDisplay();
            return;
        }
        
        const micro = data.micro;
        
        // Update spread
        const spreadElement = document.getElementById('micro-spread');
        if (spreadElement) {
            spreadElement.textContent = `${micro.spread_bps?.toFixed(1) || '--'} bps`;
        }
        
        // Update OBI
        const obiElement = document.getElementById('micro-obi');
        if (obiElement) {
            obiElement.textContent = (micro.obi?.toFixed(3) || '--');
        }
        
        // Update 5s return
        const rtnElement = document.getElementById('micro-rtn');
        if (rtnElement) {
            const rtn5s = micro.rtn_5s;
            if (rtn5s !== null && rtn5s !== undefined) {
                rtnElement.textContent = `${(rtn5s * 100).toFixed(2)}%`;
                rtnElement.style.color = rtn5s >= 0 ? '#00ff88' : '#ff4444';
            } else {
                rtnElement.textContent = '--%';
                rtnElement.style.color = '#00CFFF';
            }
        }
    }
    
    // Clear market micro display
    clearMarketMicroDisplay() {
        const spreadElement = document.getElementById('micro-spread');
        const obiElement = document.getElementById('micro-obi');
        const rtnElement = document.getElementById('micro-rtn');
        
        if (spreadElement) spreadElement.textContent = '-- bps';
        if (obiElement) obiElement.textContent = '--';
        if (rtnElement) {
            rtnElement.textContent = '--%';
            rtnElement.style.color = '#00CFFF';
        }
    }

    // Cleanup method
    destroy() {
        if (this.dataPoller) {
            this.dataPoller.stop();
        }
        if (this.aiLogsPoller) {
            this.aiLogsPoller.stop();
        }
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Initialize Dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new TradingDashboard();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        console.log('Page hidden - reducing update frequency');
    } else {
        console.log('Page visible - resuming normal updates');
    }
});
