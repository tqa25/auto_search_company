"""
Tests for AdaptiveRateLimiter — verifies adaptive delay behavior.
"""

import time
import unittest
from unittest.mock import patch

from src.rate_limiter import AdaptiveRateLimiter


class TestAdaptiveRateLimiterInit(unittest.TestCase):
    """Test initialization and validation."""

    def test_default_init(self):
        limiter = AdaptiveRateLimiter()
        self.assertEqual(limiter.current_delay, 3.0)
        self.assertEqual(limiter._min_delay, 1.0)
        self.assertEqual(limiter._max_delay, 30.0)

    def test_custom_init(self):
        limiter = AdaptiveRateLimiter(initial_delay=5.0, min_delay=2.0, max_delay=20.0)
        self.assertEqual(limiter.current_delay, 5.0)
        self.assertEqual(limiter._min_delay, 2.0)
        self.assertEqual(limiter._max_delay, 20.0)

    def test_invalid_min_delay(self):
        with self.assertRaises(ValueError):
            AdaptiveRateLimiter(min_delay=0)

    def test_invalid_max_delay(self):
        with self.assertRaises(ValueError):
            AdaptiveRateLimiter(min_delay=5.0, max_delay=2.0)

    def test_invalid_initial_delay_too_low(self):
        with self.assertRaises(ValueError):
            AdaptiveRateLimiter(initial_delay=0.5, min_delay=1.0, max_delay=10.0)

    def test_invalid_initial_delay_too_high(self):
        with self.assertRaises(ValueError):
            AdaptiveRateLimiter(initial_delay=50.0, min_delay=1.0, max_delay=10.0)


class TestReportSuccess(unittest.TestCase):
    """Test delay reduction after consecutive successes."""

    def test_delay_unchanged_before_10_successes(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        for _ in range(9):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 3.0)

    def test_delay_decreases_after_10_successes(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        for _ in range(10):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 2.5)

    def test_delay_decreases_again_after_20_successes(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        for _ in range(20):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 2.0)

    def test_delay_does_not_go_below_min(self):
        limiter = AdaptiveRateLimiter(initial_delay=2.0, min_delay=1.5)
        # 10 successes: 2.0 → 1.5
        for _ in range(10):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 1.5)
        # Another 10 successes: should stay at 1.5
        for _ in range(10):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 1.5)

    def test_consecutive_successes_counter_resets_after_decrease(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        for _ in range(10):
            limiter.report_success()
        # Counter should have been reset after the decrease
        self.assertEqual(limiter.consecutive_successes, 0)

    def test_stats_updated_on_success(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        for _ in range(5):
            limiter.report_success()
        stats = limiter.get_stats()
        self.assertEqual(stats["total_requests"], 5)
        self.assertEqual(stats["total_successes"], 5)
        self.assertEqual(stats["total_errors"], 0)


class TestReportError429(unittest.TestCase):
    """Test delay doubling on HTTP 429 (rate limit)."""

    def test_delay_doubles_on_429(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(429)
        self.assertEqual(limiter.current_delay, 6.0)

    def test_delay_doubles_again_on_second_429(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(429)
        limiter.report_error(429)
        self.assertEqual(limiter.current_delay, 12.0)

    def test_delay_capped_at_max(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0, max_delay=10.0)
        limiter.report_error(429)  # 6.0
        limiter.report_error(429)  # 10.0 (capped, not 12.0)
        self.assertEqual(limiter.current_delay, 10.0)

    def test_429_resets_consecutive_successes(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        for _ in range(5):
            limiter.report_success()
        self.assertEqual(limiter.consecutive_successes, 5)
        limiter.report_error(429)
        self.assertEqual(limiter.consecutive_successes, 0)

    def test_stats_count_rate_limits(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(429)
        stats = limiter.get_stats()
        self.assertEqual(stats["total_rate_limits"], 1)
        self.assertEqual(stats["total_errors"], 1)


class TestReportError403_503(unittest.TestCase):
    """Test max delay + 5-minute cooldown on HTTP 403/503."""

    @patch("src.rate_limiter.time.sleep")
    def test_403_sets_max_delay_and_sleeps_5min(self, mock_sleep):
        limiter = AdaptiveRateLimiter(initial_delay=3.0, max_delay=30.0)
        limiter.report_error(403)
        self.assertEqual(limiter.current_delay, 30.0)
        mock_sleep.assert_called_once_with(300)

    @patch("src.rate_limiter.time.sleep")
    def test_503_sets_max_delay_and_sleeps_5min(self, mock_sleep):
        limiter = AdaptiveRateLimiter(initial_delay=3.0, max_delay=30.0)
        limiter.report_error(503)
        self.assertEqual(limiter.current_delay, 30.0)
        mock_sleep.assert_called_once_with(300)

    @patch("src.rate_limiter.time.sleep")
    def test_stats_count_blocks(self, mock_sleep):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(403)
        limiter.report_error(503)
        stats = limiter.get_stats()
        self.assertEqual(stats["total_blocks"], 2)


class TestReportErrorOther(unittest.TestCase):
    """Test that other status codes don't change delay."""

    def test_500_does_not_change_delay(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(500)
        self.assertEqual(limiter.current_delay, 3.0)

    def test_0_network_error_does_not_change_delay(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(0)
        self.assertEqual(limiter.current_delay, 3.0)


class TestWait(unittest.TestCase):
    """Test the wait() method."""

    @patch("src.rate_limiter.time.sleep")
    def test_wait_sleeps_for_current_delay(self, mock_sleep):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.wait()
        mock_sleep.assert_called_once_with(3.0)

    @patch("src.rate_limiter.time.sleep")
    def test_wait_accumulates_total_wait_time(self, mock_sleep):
        limiter = AdaptiveRateLimiter(initial_delay=2.0)
        limiter.wait()
        limiter.wait()
        stats = limiter.get_stats()
        self.assertEqual(stats["total_wait_time"], 4.0)


class TestGetStats(unittest.TestCase):
    """Test the get_stats() method returns complete statistics."""

    def test_stats_structure(self):
        limiter = AdaptiveRateLimiter()
        stats = limiter.get_stats()
        expected_keys = {
            "current_delay", "initial_delay", "min_delay", "max_delay",
            "total_requests", "total_successes", "total_errors",
            "total_rate_limits", "total_blocks", "total_wait_time",
            "consecutive_successes", "uptime_seconds",
            "delay_changes_count", "delay_changes",
        }
        self.assertEqual(set(stats.keys()), expected_keys)

    def test_delay_changes_recorded(self):
        limiter = AdaptiveRateLimiter(initial_delay=3.0)
        limiter.report_error(429)  # 3.0 → 6.0
        stats = limiter.get_stats()
        self.assertEqual(stats["delay_changes_count"], 1)
        self.assertEqual(len(stats["delay_changes"]), 1)
        change = stats["delay_changes"][0]
        self.assertEqual(change["old_delay"], 3.0)
        self.assertEqual(change["new_delay"], 6.0)
        self.assertIn("429", change["reason"])


class TestMixedScenario(unittest.TestCase):
    """Test realistic mixed scenarios."""

    @patch("src.rate_limiter.time.sleep")
    def test_success_then_429_then_recover(self, mock_sleep):
        """Simulate: 10 successes → delay decreases, then 429 → delay doubles."""
        limiter = AdaptiveRateLimiter(initial_delay=3.0)

        # 10 successes → delay 3.0 → 2.5
        for _ in range(10):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 2.5)

        # 429 → delay doubles to 5.0
        limiter.report_error(429)
        self.assertEqual(limiter.current_delay, 5.0)

        # 10 more successes → delay 5.0 → 4.5
        for _ in range(10):
            limiter.report_success()
        self.assertEqual(limiter.current_delay, 4.5)


if __name__ == "__main__":
    unittest.main()
