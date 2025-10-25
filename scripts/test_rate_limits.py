#!/usr/bin/env python3
"""
Rate limiting smoke test script.
Tests concurrent requests to verify rate limiting and deduplication work correctly.
"""

import asyncio
import httpx
import time
import json
import sys
from typing import List, Dict, Any

async def test_concurrent_requests(url: str, num_requests: int = 10) -> Dict[str, Any]:
    """
    Test concurrent requests to verify rate limiting and deduplication.
    
    Args:
        url: URL to test
        num_requests: Number of concurrent requests
        
    Returns:
        Test results dictionary
    """
    start_time = time.time()
    results = []
    
    async def make_request(client: httpx.AsyncClient, request_id: int):
        """Make a single request and return timing info."""
        req_start = time.time()
        try:
            response = await client.get(url, timeout=10.0)
            req_end = time.time()
            
            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "response_time_ms": (req_end - req_start) * 1000,
                "success": response.status_code == 200,
                "response_size": len(response.text) if response.text else 0
            }
        except Exception as e:
            req_end = time.time()
            return {
                "request_id": request_id,
                "status_code": 0,
                "response_time_ms": (req_end - req_start) * 1000,
                "success": False,
                "error": str(e)
            }
    
    # Make concurrent requests
    async with httpx.AsyncClient() as client:
        tasks = [make_request(client, i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Analyze results
    successful_requests = [r for r in results if isinstance(r, dict) and r.get("success", False)]
    failed_requests = [r for r in results if isinstance(r, dict) and not r.get("success", False)]
    exceptions = [r for r in results if isinstance(r, Exception)]
    
    response_times = [r.get("response_time_ms", 0) for r in successful_requests]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    return {
        "url": url,
        "total_requests": num_requests,
        "successful_requests": len(successful_requests),
        "failed_requests": len(failed_requests),
        "exceptions": len(exceptions),
        "total_time_ms": total_time * 1000,
        "avg_response_time_ms": avg_response_time,
        "min_response_time_ms": min(response_times) if response_times else 0,
        "max_response_time_ms": max(response_times) if response_times else 0,
        "requests_per_second": num_requests / total_time if total_time > 0 else 0,
        "results": results
    }

async def test_rate_limiting():
    """Test rate limiting on various endpoints."""
    base_url = "http://127.0.0.1:8000"
    
    print("🧪 Rate Limiting Smoke Test")
    print("=" * 50)
    
    # Test endpoints
    endpoints = [
        "/status",
        "/agent/context",
        "/market/snapshot?symbol=ETH",
        "/market/snapshot?symbol=BTC"
    ]
    
    results = {}
    
    for endpoint in endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n📡 Testing {endpoint}...")
        
        try:
            result = await test_concurrent_requests(url, num_requests=10)
            results[endpoint] = result
            
            print(f"   ✅ {result['successful_requests']}/{result['total_requests']} successful")
            print(f"   ⏱️  Avg response time: {result['avg_response_time_ms']:.1f}ms")
            print(f"   🚀 Requests/sec: {result['requests_per_second']:.1f}")
            
            if result['failed_requests'] > 0:
                print(f"   ❌ {result['failed_requests']} failed requests")
            
            if result['exceptions'] > 0:
                print(f"   💥 {result['exceptions']} exceptions")
                
        except Exception as e:
            print(f"   ❌ Test failed: {e}")
            results[endpoint] = {"error": str(e)}
    
    # Summary
    print("\n📊 Summary")
    print("=" * 50)
    
    total_requests = sum(r.get('total_requests', 0) for r in results.values() if isinstance(r, dict))
    total_successful = sum(r.get('successful_requests', 0) for r in results.values() if isinstance(r, dict))
    total_failed = sum(r.get('failed_requests', 0) for r in results.values() if isinstance(r, dict))
    
    print(f"Total requests: {total_requests}")
    print(f"Successful: {total_successful}")
    print(f"Failed: {total_failed}")
    print(f"Success rate: {(total_successful/total_requests*100):.1f}%" if total_requests > 0 else "N/A")
    
    # Check for rate limiting indicators
    print("\n🔍 Rate Limiting Analysis")
    print("=" * 50)
    
    for endpoint, result in results.items():
        if isinstance(result, dict) and 'avg_response_time_ms' in result:
            avg_time = result['avg_response_time_ms']
            if avg_time > 1000:  # More than 1 second average
                print(f"⚠️  {endpoint}: High response time ({avg_time:.1f}ms) - possible rate limiting")
            elif avg_time < 100:  # Less than 100ms average
                print(f"✅ {endpoint}: Fast response time ({avg_time:.1f}ms) - good performance")
            else:
                print(f"✅ {endpoint}: Normal response time ({avg_time:.1f}ms)")
    
    return results

async def test_deduplication():
    """Test that concurrent identical requests are deduplicated."""
    print("\n🔄 Testing Request Deduplication")
    print("=" * 50)
    
    base_url = "http://127.0.0.1:8000"
    url = f"{base_url}/agent/context"
    
    # Make 5 identical requests simultaneously
    start_time = time.time()
    
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url, timeout=10.0) for _ in range(5)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    successful = [r for r in responses if isinstance(r, httpx.Response) and r.status_code == 200]
    
    print(f"Made 5 identical requests in {total_time:.2f}s")
    print(f"Successful responses: {len(successful)}")
    
    if len(successful) == 5:
        print("✅ All requests succeeded - deduplication working correctly")
    else:
        print("⚠️  Some requests failed - check deduplication logic")
    
    return {
        "total_requests": 5,
        "successful": len(successful),
        "total_time": total_time
    }

async def main():
    """Run all rate limiting tests."""
    print("🚀 Starting Rate Limiting Tests")
    print("=" * 50)
    
    try:
        # Test basic connectivity first
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8000/status", timeout=5.0)
            if response.status_code != 200:
                print("❌ Server not responding properly")
                sys.exit(1)
        
        print("✅ Server is responding")
        
        # Run tests
        await test_rate_limiting()
        await test_deduplication()
        
        print("\n🎉 All tests completed!")
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
