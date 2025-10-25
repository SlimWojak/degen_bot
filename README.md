# DEGEN_GOD_V2 - Professional Trading Bot

## 🚀 **CURRENT ARCHITECTURE**

### **Core Components**
- **Trading Bot** (`main.py`) - AI-powered trading engine
- **FastAPI Backend** (`backend/`) - REST API + WebSocket server
- **Professional Dashboard** (`frontend/`) - HTML/CSS/JS trading cockpit
- **Database** (`data/trades.db`) - SQLite for trade history

### **Project Structure**
```
degen_bot/
├── main.py                 # Trading bot entry point
├── bot/                    # Bot modules
│   ├── engine.py          # AI decision engine
│   ├── executor.py        # Order execution
│   ├── risk.py            # Risk management
│   └── logger.py          # Trade logging
├── utils/                  # Utilities
│   └── indicators.py      # Technical analysis
├── backend/               # FastAPI backend
│   ├── main.py           # API server
│   ├── requirements.txt  # Backend deps
│   └── Dockerfile        # Backend container
├── frontend/              # Dashboard
│   ├── index.html        # Dashboard UI
│   ├── styles.css        # Professional styling
│   ├── app.js            # Real-time updates
│   ├── nginx.conf        # Web server config
│   └── Dockerfile        # Frontend container
├── data/                  # Database
│   └── trades.db         # SQLite trade history
├── docker-compose-v2.yml  # Container orchestration
└── requirements.txt       # Bot dependencies
```

## 🚀 **Run Modes**

### **Development Mode**
```bash
make dev
# Starts uvicorn server with auto-reload
# Reads from .env file
```

### **Production Mode**
```bash
make up
# Starts docker-compose services
# Reads from .env file
```

### **Testing**
```bash
make test
# Runs pytest on backend tests
```

## 🔧 **Environment Variables**

### **Core Hyperliquid Settings**
- `HL_NETWORK` - Network (mainnet/testnet)
- `HL_ACCOUNT_ADDRESS` - Main account address
- `HL_PRIVATE_KEY` - API wallet private key
- `HL_SYMBOL` - Default trading symbol (ETH)
- `HL_NOTIONAL_USD` - Default notional amount (15)

### **Data Source Configuration**
- `DATA_SOURCE` - Data source (mock/live)
- `STATE_CACHE_MS` - Cache TTL in milliseconds (800)
- `HL_DEFAULT_SYMBOL` - Default symbol for health checks (ETH)

### **Trading Configuration**
- `HL_TRADING_ENABLED` - Enable trading (true/false)
- `HL_MAX_NOTIONAL_USD` - Max notional per trade (1000)
- `HL_MAX_CROSS_BPS` - Max cross percentage (100 = 1%)

### **Signer Implementation**
- `HL_SIGNER_IMPL` - Signer implementation (sdk/custom)

### **Legacy (Deprecated)**
- `HL_ENV` - Use `HL_NETWORK` instead
- `HL_API_WALLET_ADDRESS` - Use `HL_ACCOUNT_ADDRESS` instead

## 🔗 **Hyperliquid Connectivity**

### **Quick Start**
1. Copy `config.example.env` → `.env` and fill values
2. Authorize the signer address in HL UI (Settings → API)
3. `make up` or `make dev`
4. GET `/hl/preflight` → should show network, addresses
5. POST `/hl/ioc_roundtrip` → places test trade

### **Notes**
- SDK pinned: `hyperliquid-python-sdk==0.20.0`
- API: `order(name, is_buy, sz, limit_px, order_type, reduce_only=False, ...)`
- Price discovery: `l2_snapshot → all_mids`
- Precision: size & price quantization, adaptive tick snapping

## 🎯 **CURRENT STATUS**

### **✅ WORKING COMPONENTS**
- **Trading Bot**: Running with simulated data
- **FastAPI Backend**: Serving real-time data APIs
- **Professional Dashboard**: Clean, responsive UI
- **Database**: 7 simulated trades stored
- **Docker**: All services containerized
- **Hyperliquid Integration**: Canonical L1 signing with adaptive tick snapping

### **❌ NOT YET LIVE**
- **Real Trading**: Currently in test/simulation mode
- **Live Data**: Dashboard shows simulated data, not live account balance

## 🚀 **DEPLOYMENT**

### **Start All Services**
```bash
docker-compose -f docker-compose-v2.yml up -d --build
```

### **Access Dashboard**
- **URL**: http://localhost:80
- **Status**: Professional trading cockpit with real-time updates

### **Services**
- **Bot**: Port 8080 (health check)
- **Backend**: Port 8000 (API + WebSocket)
- **Frontend**: Port 80 (Dashboard)

## 🔧 **NEXT STEPS FOR LIVE TRADING**

1. **Fix Hyperliquid Connection** - Resolve 422 deserialize errors
2. **Configure Live API Keys** - Connect to real Hyperliquid account
3. **Enable Live Trading** - Switch from simulation to live mode
4. **Verify Live Data** - Ensure dashboard shows real account balance

## 📊 **DASHBOARD FEATURES**

- **Real-time Updates**: WebSocket + API polling
- **Professional UI**: Dark theme, responsive design
- **Live Metrics**: Portfolio value, win rate, Sharpe ratio
- **Equity Curve**: Interactive Chart.js visualization
- **Active Positions**: Real-time position tracking
- **AI Insights**: DeepSeek decision logging
- **Trade History**: Complete trade log with P&L

## 🛠️ **TECHNOLOGY STACK**

- **Backend**: FastAPI + WebSocket + SQLite
- **Frontend**: HTML5 + CSS3 + JavaScript + Chart.js
- **Bot**: Python + Hyperliquid SDK + DeepSeek API
- **Infrastructure**: Docker + Docker Compose + Nginx
- **Database**: SQLite with Pandas integration

---

**Status**: Ready for live trading setup
**Last Updated**: October 24, 2025