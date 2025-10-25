# 🚀 PesoEcho Trading System

**AI-driven autonomous trading on Hyperliquid with DeepSeek integration**

[![Phase ε.1](https://img.shields.io/badge/Phase-ε.1%20Purification%20Pass-brightgreen)](https://github.com/SlimWojak/degen_bot/milestone/1)
[![Python](https://img.shields.io/badge/Python-3.9+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

## 🎯 Overview

PesoEcho is a sophisticated AI trading system designed for autonomous cryptocurrency trading on the Hyperliquid exchange. The system integrates DeepSeek's advanced language models to make intelligent trading decisions while maintaining strict safety controls and risk management.

## ✨ Key Features

### 🤖 AI-Powered Decision Making
- **DeepSeek Integration**: Advanced language model for market analysis
- **Reasoning Engine**: Structured decision-making with confidence scoring
- **Learning Loop**: Continuous improvement through performance feedback
- **Adaptive Scoring**: Dynamic position sizing based on performance

### 🛡️ Safety & Risk Management
- **Live Guard**: Multi-layer safety controls for live trading
- **Circuit Breakers**: Automatic trading halt on repeated failures
- **Budget Guards**: Drawdown protection with configurable limits
- **Idempotency**: Duplicate order prevention with intent tracking

### 📊 Real-time Market Data
- **Unified WebSocket Feed**: Single connection for all market data
- **Rate Limiting**: Token bucket algorithm for API compliance
- **Data Quality Monitoring**: Continuous health checks and alerts
- **Stale Data Fallback**: Graceful degradation when data is unavailable

### 🔧 Production-Ready Infrastructure
- **Async Hygiene**: Supervised tasks with timeout protection
- **Deterministic Testing**: Seeded randomness and frozen time
- **Type Safety**: Comprehensive typing with Protocols
- **Error Handling**: Centralized exceptions and structured responses
- **Dependency Management**: Clean requirements and audit tools

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   Hyperliquid   │
│   (Dashboard)   │◄──►│   (FastAPI)     │◄──►│   (Exchange)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   DeepSeek AI   │
                       │   (Reasoning)   │
                       └─────────────────┘
```

### Core Components

- **PesoMind**: Central orchestrator for reasoning, execution, and reflection
- **MarketFeedManager**: Unified WebSocket connection management
- **OrderBus**: Safe order execution with idempotency and audit trails
- **SimBroker**: In-memory simulation for testing and validation
- **StateService**: Cached market and account data with staleness tracking

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 16+ (for frontend)
- Docker (optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/SlimWojak/degen_bot.git
   cd degen_bot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp config.example.env .env
   # Edit .env with your configuration
   ```

4. **Start the system**
   ```bash
   make start
   ```

### Development Setup

```bash
# Setup development environment
make dev

# Run all checks
make check

# Run tests
make test

# Generate reports
make reports
```

## 📋 Current Status

### ✅ Phase ε.1: Purification Pass (Complete)
- **Async Hygiene**: Supervised tasks with timeout protection
- **Deterministic Tests**: Comprehensive test suite with seeded randomness
- **Dependency Hygiene**: Clean requirements and audit tools
- **Type Safety**: Protocols and TypedDict models
- **Error Handling**: Centralized exceptions and structured responses
- **Static Analysis**: Pre-commit hooks and CI tools

### 🔄 Next: Phase ε.2: Async Event Loop Fixes
- Fix remaining async event loop issues in deterministic tests
- Install and configure ruff/mypy for full static analysis
- Clean up phantom dependencies in production
- Add comprehensive test coverage reporting

## 🧪 Testing

The system includes comprehensive deterministic testing:

```bash
# Run all tests
python tests/test_simple_truth.py

# Run specific test suites
pytest tests/test_market_cache.py -v
pytest tests/test_hyperliquid_ws.py -v
pytest tests/test_idempotency_deterministic.py -v
```

## 📊 Monitoring & Observability

- **Health Endpoints**: `/status`, `/ops/metrics`, `/ops/data-health`
- **Structured Logging**: JSON-formatted logs with rotation
- **Audit Trails**: Complete order and decision tracking
- **Performance Metrics**: Rate limiting, WebSocket health, AI performance

## 🔒 Security & Safety

- **Environment Guards**: Multiple layers of live trading protection
- **Input Validation**: Comprehensive order and data validation
- **Error Sanitization**: Prevents information leakage in error messages
- **Audit Logging**: Complete trail of all system decisions and actions

## 📚 Documentation

- [API Documentation](docs/api.md)
- [Configuration Guide](docs/configuration.md)
- [Deployment Guide](docs/deployment.md)
- [Contributing Guide](docs/contributing.md)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](docs/contributing.md) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Hyperliquid**: For the excellent trading infrastructure
- **DeepSeek**: For the advanced AI capabilities
- **FastAPI**: For the robust web framework
- **Pydantic**: For the excellent data validation

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/SlimWojak/degen_bot/issues)
- **Discussions**: [GitHub Discussions](https://github.com/SlimWojak/degen_bot/discussions)
- **Documentation**: [Project Wiki](https://github.com/SlimWojak/degen_bot/wiki)

---

**⚠️ Disclaimer**: This software is for educational and research purposes. Trading cryptocurrencies involves substantial risk of loss. Use at your own risk.