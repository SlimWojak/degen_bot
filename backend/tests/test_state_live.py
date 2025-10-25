"""
Tests for live state service integration.
Tests both mock and live data modes.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from backend.services.state_service import StateService
from backend.config import settings

class TestStateService:
    """Test state service functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        self.service = StateService()
    
    @pytest.mark.asyncio
    async def test_mock_metrics(self):
        """Test mock metrics data."""
        # Set to mock mode
        with patch.object(settings, 'DATA_SOURCE', 'mock'):
            metrics = await self.service.get_metrics()
            
            assert isinstance(metrics, dict)
            assert 'total_value' in metrics
            assert 'win_rate' in metrics
            assert 'sharpe' in metrics
            assert 'max_dd' in metrics
            assert 'trades' in metrics
            assert 'best_pnl' in metrics
            assert 'worst_pnl' in metrics
    
    @pytest.mark.asyncio
    async def test_mock_positions(self):
        """Test mock positions data."""
        with patch.object(settings, 'DATA_SOURCE', 'mock'):
            positions = await self.service.get_positions()
            
            assert isinstance(positions, list)
            if positions:  # If mock data exists
                pos = positions[0]
                assert 'side' in pos
                assert 'coin' in pos
                assert 'entry' in pos
                assert 'current' in pos
                assert 'qty' in pos
                assert 'pnl' in pos
    
    @pytest.mark.asyncio
    async def test_mock_trades(self):
        """Test mock trades data."""
        with patch.object(settings, 'DATA_SOURCE', 'mock'):
            trades = await self.service.get_trades()
            
            assert isinstance(trades, list)
            if trades:  # If mock data exists
                trade = trades[0]
                assert 'side' in trade
                assert 'coin' in trade
                assert 'entry' in trade
                assert 'exit' in trade
                assert 'qty' in trade
                assert 'pnl' in trade
    
    @pytest.mark.asyncio
    async def test_mock_equity(self):
        """Test mock equity data."""
        with patch.object(settings, 'DATA_SOURCE', 'mock'):
            equity = await self.service.get_equity()
            
            assert isinstance(equity, list)
            if equity:  # If mock data exists
                point = equity[0]
                assert 'timestamp' in point
                assert 'value' in point
    
    @pytest.mark.asyncio
    async def test_live_metrics_with_mock_hl(self):
        """Test live metrics with mocked Hyperliquid client."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            # Mock the connect function
            mock_exchange = Mock()
            mock_info = Mock()
            
            # Mock portfolio data
            mock_portfolio = {
                'totalValue': 15000,
                'assetPositions': []
            }
            mock_info.portfolio.return_value = mock_portfolio
            
            # Mock user fills
            mock_fills = [
                {'pnl': 100, 'coin': 'ETH', 'isBuy': True, 'px': 3000, 'sz': 1, 'time': 1000000},
                {'pnl': -50, 'coin': 'BTC', 'isBuy': False, 'px': 50000, 'sz': 0.1, 'time': 1000001}
            ]
            mock_info.user_fills.return_value = mock_fills
            
            with patch('backend.services.state_service.connect', return_value=(mock_exchange, mock_info)):
                metrics = await self.service.get_metrics()
                
                assert isinstance(metrics, dict)
                assert 'total_value' in metrics
                assert metrics['total_value'] == 15000
                assert 'win_rate' in metrics
                assert 'trades' in metrics
                assert metrics['trades'] == 2
    
    @pytest.mark.asyncio
    async def test_live_positions_with_mock_hl(self):
        """Test live positions with mocked Hyperliquid client."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            mock_exchange = Mock()
            mock_info = Mock()
            
            # Mock portfolio with positions
            mock_portfolio = {
                'totalValue': 15000,
                'assetPositions': [
                    {
                        'coin': 'ETH',
                        'position': {
                            'szi': 2.5,
                            'entryPx': 3000,
                            'positionValue': 7500,
                            'unrealizedPnl': 250
                        }
                    }
                ]
            }
            mock_info.portfolio.return_value = mock_portfolio
            
            with patch('backend.services.state_service.connect', return_value=(mock_exchange, mock_info)):
                positions = await self.service.get_positions()
                
                assert isinstance(positions, list)
                assert len(positions) == 1
                
                pos = positions[0]
                assert pos['side'] == 'long'
                assert pos['coin'] == 'ETH'
                assert pos['qty'] == 2.5
                assert pos['pnl'] == 250
    
    @pytest.mark.asyncio
    async def test_live_trades_with_mock_hl(self):
        """Test live trades with mocked Hyperliquid client."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            mock_exchange = Mock()
            mock_info = Mock()
            
            # Mock user fills
            mock_fills = [
                {
                    'coin': 'ETH',
                    'isBuy': True,
                    'px': 3000,
                    'sz': 1.0,
                    'pnl': 100,
                    'time': 1000000000
                }
            ]
            mock_info.user_fills.return_value = mock_fills
            
            with patch('backend.services.state_service.connect', return_value=(mock_exchange, mock_info)):
                trades = await self.service.get_trades()
                
                assert isinstance(trades, list)
                assert len(trades) == 1
                
                trade = trades[0]
                assert trade['side'] == 'long'
                assert trade['coin'] == 'ETH'
                assert trade['pnl'] == 100
                assert '_meta' in trade
                assert trade['_meta']['source'] == 'live'
    
    @pytest.mark.asyncio
    async def test_live_equity_with_mock_hl(self):
        """Test live equity with mocked Hyperliquid client."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            mock_exchange = Mock()
            mock_info = Mock()
            
            # Mock portfolio
            mock_portfolio = {
                'totalValue': 15000
            }
            mock_info.portfolio.return_value = mock_portfolio
            
            with patch('backend.services.state_service.connect', return_value=(mock_exchange, mock_info)):
                equity = await self.service.get_equity()
                
                assert isinstance(equity, list)
                assert len(equity) == 1
                
                point = equity[0]
                assert 'timestamp' in point
                assert 'value' in point
                assert point['value'] == 15000
                assert '_meta' in point
                assert point['_meta']['source'] == 'live'
    
    @pytest.mark.asyncio
    async def test_status_health_checks(self):
        """Test status health checks."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            # Mock successful health checks
            with patch.object(self.service, '_test_price_discovery', return_value=3000):
                with patch.object(self.service, '_test_exchange_connection', return_value=True):
                    with patch.object(self.service, '_get_last_trade_time', return_value=1234567890):
                        status = await self.service.get_status()
                        
                        assert isinstance(status, dict)
                        assert 'market' in status
                        assert 'api' in status
                        assert 'db' in status
                        assert 'ws' in status
                        assert 'bot' in status
                        
                        assert status['market'] == 'ok'
                        assert status['api'] == 'healthy'
                        assert status['bot'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in live mode."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            # Mock connection failure
            with patch('backend.services.state_service.connect', side_effect=Exception("Connection failed")):
                metrics = await self.service.get_metrics()
                
                # Should return error metadata
                assert '_meta' in metrics
                assert 'error' in metrics['_meta']
                assert 'insufficient' in metrics['_meta']
    
    @pytest.mark.asyncio
    async def test_cache_behavior(self):
        """Test caching behavior."""
        with patch.object(settings, 'DATA_SOURCE', 'live'):
            mock_exchange = Mock()
            mock_info = Mock()
            mock_info.portfolio.return_value = {'totalValue': 10000}
            mock_info.user_fills.return_value = []
            
            with patch('backend.services.state_service.connect', return_value=(mock_exchange, mock_info)):
                # First call should hit the service
                metrics1 = await self.service.get_metrics()
                
                # Second call should use cache (if within TTL)
                metrics2 = await self.service.get_metrics()
                
                assert isinstance(metrics1, dict)
                assert isinstance(metrics2, dict)

if __name__ == "__main__":
    pytest.main([__file__])
