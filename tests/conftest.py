"""
Pytest Configuration - Phase ε.1 Purification Pass
Provides async fixtures, deterministic time, and proper test teardown.
"""

import asyncio
import os
import pytest
import random
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

# Set deterministic seed for all tests
RNG_SEED = int(os.getenv("RNG_SEED", "1337"))
random.seed(RNG_SEED)

# Seed numpy if available
try:
    import numpy as np
    np.random.seed(RNG_SEED)
except ImportError:
    pass

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def async_fixture():
    """Base async fixture for all async tests."""
    # Set up deterministic environment
    os.environ["RNG_SEED"] = str(RNG_SEED)
    
    yield
    
    # Cleanup: cancel any remaining tasks
    tasks = [task for task in asyncio.all_tasks() if not task.done()]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def deterministic_time():
    """Provide deterministic time for tests."""
    from backend.util.async_tools import get_deterministic_clock
    
    clock = get_deterministic_clock()
    clock.freeze()
    
    yield clock
    
    clock.unfreeze()

@pytest.fixture
def seeded_random():
    """Provide seeded random number generator."""
    # Reset seed for each test
    random.seed(RNG_SEED)
    
    try:
        import numpy as np
        np.random.seed(RNG_SEED)
    except ImportError:
        pass
    
    yield random

@pytest.fixture(autouse=True)
def setup_test_env():
    """Set up test environment variables."""
    # Ensure we're in test mode
    os.environ["HL_TRADING_ENABLED"] = "false"
    os.environ["MIND_MODE"] = "sim"
    os.environ["LLM_PROVIDER"] = "mock"
    
    yield
    
    # Cleanup environment
    for key in ["HL_TRADING_ENABLED", "MIND_MODE", "LLM_PROVIDER"]:
        os.environ.pop(key, None)

@pytest.fixture
async def mock_websocket():
    """Mock WebSocket connection for tests."""
    class MockWebSocket:
        def __init__(self):
            self.connected = True
            self.messages = []
        
        async def send(self, message):
            self.messages.append(message)
        
        async def recv(self):
            # Return mock market data
            return '{"type":"trades","data":[{"symbol":"BTC","price":42000,"size":0.1,"timestamp":1640995200000}]}'
        
        async def close(self):
            self.connected = False
    
    return MockWebSocket()

@pytest.fixture
async def mock_hl_client():
    """Mock Hyperliquid client for tests."""
    class MockHLClient:
        def __init__(self):
            self.connected = True
        
        async def get_account_info(self):
            return {
                "accountValue": "10000.0",
                "totalMarginUsed": "1000.0",
                "totalNtlPos": "5000.0"
            }
        
        async def get_positions(self):
            return []
        
        async def get_trades(self):
            return []
    
    return MockHLClient()

@pytest.fixture
def mock_market_data():
    """Provide mock market data for tests."""
    return {
        "BTC": {
            "price": 42000.0,
            "price_change_24h": 1000.0,
            "funding_rate": 0.01,
            "open_interest": 1.2,
            "volume_24h": 1000.0,
            "spread_bps": 0.2
        },
        "ETH": {
            "price": 3000.0,
            "price_change_24h": 100.0,
            "funding_rate": 0.005,
            "open_interest": 0.8,
            "volume_24h": 500.0,
            "spread_bps": 0.3
        }
    }

# Pytest configuration
def pytest_configure(config):
    """Configure pytest with deterministic settings."""
    # Add custom markers
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "deterministic: marks tests as deterministic")

def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Mark async tests
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
        
        # Mark deterministic tests
        if "deterministic" in item.name or "test_truth" in item.name:
            item.add_marker(pytest.mark.deterministic)
