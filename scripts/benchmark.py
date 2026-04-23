"""
Benchmark Script — Compare fixed delay vs AdaptiveRateLimiter performance.

This script measures the overhead and effectiveness of AdaptiveRateLimiter
compared to a fixed delay approach. It uses simulated API calls (mocks)
to avoid consuming real Firecrawl credits.

Usage:
    python scripts/benchmark.py
"""

import time
import sys
import os

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rate_limiter import AdaptiveRateLimiter


def simulate_api_calls_fixed_delay(n_requests: int, delay: float = 3.0) -> dict:
    """Simulate n API calls with a fixed delay between each.
    
    Args:
        n_requests: Number of simulated API calls.
        delay: Fixed delay in seconds between calls.
    
    Returns:
        Dict with timing results.
    """
    start = time.time()
    total_delay = 0.0
    
    for i in range(n_requests):
        # Simulate API call (instant mock)
        _ = f"result_{i}"
        
        # Fixed delay between calls (skip last)
        if i < n_requests - 1:
            time.sleep(delay)
            total_delay += delay
    
    elapsed = time.time() - start
    
    return {
        "method": "Fixed Delay",
        "requests": n_requests,
        "delay_per_request": delay,
        "total_delay_time": round(total_delay, 2),
        "total_elapsed": round(elapsed, 2),
        "avg_per_request": round(elapsed / n_requests, 3),
    }


def simulate_api_calls_adaptive(n_requests: int, initial_delay: float = 3.0,
                                  error_pattern: list = None) -> dict:
    """Simulate n API calls with AdaptiveRateLimiter.
    
    Args:
        n_requests: Number of simulated API calls.
        initial_delay: Starting delay for the rate limiter.
        error_pattern: Optional list of (request_index, status_code) tuples
                       to simulate errors at specific points.
    
    Returns:
        Dict with timing results.
    """
    error_map = {}
    if error_pattern:
        for idx, code in error_pattern:
            error_map[idx] = code
    
    limiter = AdaptiveRateLimiter(initial_delay=initial_delay)
    
    start = time.time()
    
    for i in range(n_requests):
        # Wait according to adaptive delay
        limiter.wait()
        
        # Simulate API call
        if i in error_map:
            status_code = error_map[i]
            limiter.report_error(status_code)
        else:
            limiter.report_success()
    
    elapsed = time.time() - start
    stats = limiter.get_stats()
    
    return {
        "method": "Adaptive Rate Limiter",
        "requests": n_requests,
        "initial_delay": initial_delay,
        "final_delay": stats["current_delay"],
        "total_wait_time": stats["total_wait_time"],
        "total_elapsed": round(elapsed, 2),
        "avg_per_request": round(elapsed / n_requests, 3),
        "delay_changes": stats["delay_changes_count"],
        "rate_limit_errors": stats["total_rate_limits"],
    }


def print_comparison_table(fixed_result: dict, adaptive_result: dict):
    """Print a formatted comparison table."""
    print("\n" + "=" * 70)
    print("  BENCHMARK RESULTS: Fixed Delay vs Adaptive Rate Limiter")
    print("=" * 70)
    
    headers = ["Metric", "Fixed Delay", "Adaptive"]
    rows = [
        ("Requests", fixed_result["requests"], adaptive_result["requests"]),
        ("Total Elapsed (s)", fixed_result["total_elapsed"], adaptive_result["total_elapsed"]),
        ("Avg per Request (s)", fixed_result["avg_per_request"], adaptive_result["avg_per_request"]),
        ("Total Delay Time (s)", fixed_result["total_delay_time"], adaptive_result["total_wait_time"]),
        ("Final Delay (s)", fixed_result["delay_per_request"], adaptive_result["final_delay"]),
        ("Delay Changes", "N/A", adaptive_result["delay_changes"]),
        ("Rate Limit Errors", "N/A", adaptive_result["rate_limit_errors"]),
    ]
    
    # Print table
    col_widths = [25, 15, 15]
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(f"\n  {header_line}")
    print(f"  {'-' * (sum(col_widths) + 6)}")
    
    for label, fixed_val, adaptive_val in rows:
        row = f"  {str(label).ljust(col_widths[0])} | {str(fixed_val).ljust(col_widths[1])} | {str(adaptive_val).ljust(col_widths[2])}"
        print(row)
    
    # Calculate improvement
    if fixed_result["total_elapsed"] > 0:
        improvement = (1 - adaptive_result["total_elapsed"] / fixed_result["total_elapsed"]) * 100
        print(f"\n  📊 Time improvement: {improvement:+.1f}%")
        if improvement > 0:
            print(f"  ✅ Adaptive is {improvement:.1f}% faster")
        else:
            print(f"  ⚠️  Adaptive is {abs(improvement):.1f}% slower (expected with small N)")
    
    print("=" * 70)


def main():
    print("🚀 Starting Performance Benchmark")
    print("   (Using simulated API calls — no real credits consumed)\n")
    
    n_requests = 20
    fixed_delay = 3.0
    
    # ----- Scenario 1: All successes -----
    print(f"📋 Scenario 1: {n_requests} requests, all successful")
    print("   Fixed Delay: constant 3.0s between requests")
    print("   Adaptive: starts at 3.0s, decreases after 10 successes\n")
    
    print("   Running fixed delay benchmark...")
    fixed_result = simulate_api_calls_fixed_delay(n_requests, delay=fixed_delay)
    print(f"   ✅ Done: {fixed_result['total_elapsed']}s")
    
    print("   Running adaptive benchmark...")
    adaptive_result = simulate_api_calls_adaptive(n_requests, initial_delay=fixed_delay)
    print(f"   ✅ Done: {adaptive_result['total_elapsed']}s")
    
    print_comparison_table(fixed_result, adaptive_result)
    
    # ----- Scenario 2: With rate limit errors -----
    print(f"\n📋 Scenario 2: {n_requests} requests, with 1 rate limit (429) at request #5")
    print("   Tests adaptive recovery after error\n")
    
    print("   Running adaptive benchmark with error...")
    adaptive_with_error = simulate_api_calls_adaptive(
        n_requests,
        initial_delay=fixed_delay,
        error_pattern=[(5, 429)]
    )
    print(f"   ✅ Done: {adaptive_with_error['total_elapsed']}s")
    
    print(f"\n  Rate Limit Recovery:")
    print(f"    - Delay after 429: {adaptive_with_error['final_delay']}s")
    print(f"    - Total delay changes: {adaptive_with_error['delay_changes']}")
    print(f"    - Total elapsed: {adaptive_with_error['total_elapsed']}s")
    
    # ----- Summary -----
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  For {n_requests} requests:")
    print(f"    Fixed:    {fixed_result['total_elapsed']}s total, {fixed_result['avg_per_request']}s avg")
    print(f"    Adaptive: {adaptive_result['total_elapsed']}s total, {adaptive_result['avg_per_request']}s avg")
    print(f"    With err: {adaptive_with_error['total_elapsed']}s total")
    print()
    print("  📌 Note: Adaptive delay shows more benefit over longer runs (100+ requests)")
    print("     where the delay gradually decreases from 3.0s to the minimum 1.0s,")
    print("     potentially saving ~2s per request = ~3.3 hours for 6,000 companies.")
    print("=" * 70)


if __name__ == "__main__":
    main()
