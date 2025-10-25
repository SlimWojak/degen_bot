#!/usr/bin/env python3
"""
Test script to trip circuit breaker manually.
Simulates failures to test breaker functionality.
"""

import requests
import time
import json

def test_breaker_trip():
    """Test circuit breaker by simulating failures."""
    base_url = "http://127.0.0.1:8000"
    
    print("Testing circuit breaker...")
    
    # Get initial breaker status
    try:
        response = requests.get(f"{base_url}/ops/breakers", timeout=5)
        print(f"Initial breaker status: {response.json()}")
    except Exception as e:
        print(f"Error getting breaker status: {e}")
    
    # Simulate failures by making requests that will fail
    print("\nSimulating failures...")
    for i in range(6):  # More than the threshold of 5
        try:
            # This should trigger the breaker
            response = requests.get(f"{base_url}/agent/context", timeout=1)
            print(f"Request {i+1}: {response.status_code}")
        except Exception as e:
            print(f"Request {i+1} failed: {e}")
        
        time.sleep(0.1)
    
    # Check breaker status after failures
    try:
        response = requests.get(f"{base_url}/ops/breakers", timeout=5)
        print(f"\nBreaker status after failures: {response.json()}")
    except Exception as e:
        print(f"Error getting breaker status: {e}")
    
    # Test cockpit endpoint
    try:
        response = requests.get(f"{base_url}/ops/cockpit", timeout=5)
        cockpit_data = response.json()
        print(f"\nCockpit data: {json.dumps(cockpit_data, indent=2)}")
    except Exception as e:
        print(f"Error getting cockpit data: {e}")

if __name__ == "__main__":
    test_breaker_trip()
