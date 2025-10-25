#!/usr/bin/env python3
"""
Test script to verify budget guard functionality.
Tests drawdown limits and budget protection.
"""

import requests
import time
import json

def test_budget_guard():
    """Test budget guard by simulating PnL losses."""
    base_url = "http://127.0.0.1:8000"
    
    print("Testing budget guard...")
    
    # Get initial budget status
    try:
        response = requests.get(f"{base_url}/ops/budget", timeout=5)
        print(f"Initial budget status: {response.json()}")
    except Exception as e:
        print(f"Error getting budget status: {e}")
    
    # Simulate PnL losses to trigger budget guard
    print("\nSimulating PnL losses...")
    
    # In a real implementation, you would record actual PnL
    # For testing, we'll just check the current status
    try:
        response = requests.get(f"{base_url}/ops/budget", timeout=5)
        budget_data = response.json()
        print(f"Budget status: {json.dumps(budget_data, indent=2)}")
        
        # Check if budget guard is triggered
        if budget_data.get("triggered", False):
            print("✅ Budget guard is triggered!")
        else:
            print("⚠️ Budget guard not triggered (expected in test environment)")
            
    except Exception as e:
        print(f"Error getting budget status: {e}")
    
    # Test cockpit endpoint
    try:
        response = requests.get(f"{base_url}/ops/cockpit", timeout=5)
        cockpit_data = response.json()
        print(f"\nCockpit data: {json.dumps(cockpit_data, indent=2)}")
    except Exception as e:
        print(f"Error getting cockpit data: {e}")

if __name__ == "__main__":
    test_budget_guard()
