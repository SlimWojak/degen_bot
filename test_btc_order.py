#!/usr/bin/env python3
"""
Test script for $10 BTC IOC order using the updated signing implementation.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from bot.executor import OrderExecutor
from common.config import load_config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_btc_order():
    """Test a $10 BTC IOC order."""
    try:
        # Load configuration
        config = load_config()
        
        # Initialize the order executor
        executor = OrderExecutor(
            account_address=config.hl.account,
            signer_private_key=config.hl.private_key,
            base_url=config.hl.rest_url
        )
        
        logger.info("🚀 Starting $10 BTC IOC order test...")
        
        # Place a $10 BTC buy order
        result = await executor.place_order(
            coin="BTC",
            usd_amount=10.0,
            is_buy=True
        )
        
        logger.info(f"📊 Order result: {result}")
        
        # Check if the order was successful
        if result and result.get('oid'):
            logger.info(f"✅ Order placed successfully! OID: {result['oid']}")
            
            # Check the raw response for success criteria
            raw_response = result.get('raw', {})
            if isinstance(raw_response, dict):
                status = raw_response.get('status')
                if status == 'ok':
                    logger.info("✅ Order status: OK")
                    
                    # Check for specific success indicators
                    data = raw_response.get('data', {})
                    if 'statuses' in data:
                        statuses = data['statuses']
                        if statuses:
                            first_status = statuses[0]
                            logger.info(f"📋 First status: {first_status}")
                            
                            # Check for success indicators
                            if 'resting' in first_status:
                                logger.info("✅ Order is resting (success)")
                            elif 'filled' in first_status:
                                logger.info("✅ Order is filled (success)")
                            elif 'error' in first_status:
                                error_info = first_status['error']
                                logger.warning(f"⚠️ Order error: {error_info}")
                                
                                # Check for specific error messages
                                if 'min notional' in str(error_info).lower():
                                    logger.info("✅ Got 'min notional' response (expected for small orders)")
                                elif 'user or api wallet does not exist' in str(error_info).lower():
                                    logger.error("❌ Authentication failed - check API credentials")
                                else:
                                    logger.warning(f"⚠️ Unexpected error: {error_info}")
                            else:
                                logger.info(f"📋 Status details: {first_status}")
                else:
                    logger.error(f"❌ Order failed with status: {status}")
                    logger.error(f"📋 Full response: {raw_response}")
            else:
                logger.warning(f"⚠️ Unexpected raw response format: {raw_response}")
        else:
            logger.error("❌ No order ID returned - order failed")
            logger.error(f"📋 Full result: {result}")
            
    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_btc_order())
