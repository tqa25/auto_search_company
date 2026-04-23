"""
Rate Limiter — Adaptive rate-limiting for external API requests.

This module implements an adaptive delay strategy that automatically adjusts
request pacing based on API response codes:
  - Consecutive successes → gradually decrease delay (faster throughput)
  - HTTP 429 (rate limit) → double the delay
  - HTTP 403/503 (potential ban) → max delay + 5-minute cooldown

Design Principle: STABILITY over SPEED. Running slowly but completing all
6,000+ companies is better than running fast and getting banned.

Dependencies:
  - None (standalone module)
"""

import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts delay based on API response patterns."""

    def __init__(
        self,
        initial_delay: float = 3.0,
        min_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        """Initialize the AdaptiveRateLimiter.

        Args:
            initial_delay: Starting delay between requests in seconds.
            min_delay: Minimum allowed delay (floor).
            max_delay: Maximum allowed delay (ceiling).
        """
        if min_delay <= 0:
            raise ValueError("min_delay must be positive")
        if max_delay < min_delay:
            raise ValueError("max_delay must be >= min_delay")
        if initial_delay < min_delay or initial_delay > max_delay:
            raise ValueError("initial_delay must be between min_delay and max_delay")

        self._initial_delay = initial_delay
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._current_delay = initial_delay

        # Consecutive success counter (resets on any error)
        self._consecutive_successes = 0

        # Statistics
        self._total_requests = 0
        self._total_successes = 0
        self._total_errors = 0
        self._total_rate_limits = 0   # HTTP 429
        self._total_blocks = 0         # HTTP 403/503
        self._total_wait_time = 0.0
        self._delay_changes: list[dict] = []
        self._created_at = datetime.now()

    # ------------------------------------------------------------------
    # Core public methods
    # ------------------------------------------------------------------

    def wait(self):
        """Sleep for the current adaptive delay.

        Call this BEFORE making a request to pace API calls.
        """
        delay = self._current_delay
        self._total_wait_time += delay
        time.sleep(delay)

    def report_success(self):
        """Report a successful API request.

        After 10 consecutive successes, decreases delay by 0.5s
        (down to min_delay).
        """
        self._total_requests += 1
        self._total_successes += 1
        self._consecutive_successes += 1

        # Every 10 consecutive successes → decrease delay
        if self._consecutive_successes >= 10:
            old_delay = self._current_delay
            new_delay = max(self._current_delay - 0.5, self._min_delay)

            if new_delay != old_delay:
                self._current_delay = new_delay
                self._log_delay_change(
                    old_delay, new_delay,
                    reason=f"10 consecutive successes ({self._consecutive_successes} total)"
                )

            # Reset the counter (don't accumulate indefinitely)
            self._consecutive_successes = 0

    def report_error(self, status_code: int):
        """Report an API error with specific HTTP status code.

        Args:
            status_code: HTTP status code received.
                - 429: Rate limit → double delay
                - 403/503: Potential block → max delay + 5-minute cooldown
                - Others: log but don't change delay
        """
        self._total_requests += 1
        self._total_errors += 1
        self._consecutive_successes = 0  # Reset success streak

        old_delay = self._current_delay

        if status_code == 429:
            # Rate limited → double delay
            self._total_rate_limits += 1
            new_delay = min(self._current_delay * 2, self._max_delay)
            self._current_delay = new_delay
            self._log_delay_change(
                old_delay, new_delay,
                reason=f"HTTP 429 (rate limited)"
            )

        elif status_code in (403, 503):
            # Potential IP ban / service unavailable → max delay + long cooldown
            self._total_blocks += 1
            self._current_delay = self._max_delay
            self._log_delay_change(
                old_delay, self._max_delay,
                reason=f"HTTP {status_code} (potential block) — waiting 5 minutes"
            )
            # 5-minute cooldown
            logger.warning(
                f"HTTP {status_code} detected. Entering 5-minute cooldown "
                f"to avoid IP ban."
            )
            time.sleep(300)  # 5 minutes
            self._total_wait_time += 300

        else:
            # Other errors: log but don't change delay
            logger.warning(
                f"HTTP {status_code} error. Delay unchanged at {self._current_delay}s."
            )

    def get_stats(self) -> dict:
        """Return aggregate statistics about rate limiter usage.

        Returns:
            Dict with keys:
                current_delay, initial_delay, min_delay, max_delay,
                total_requests, total_successes, total_errors,
                total_rate_limits, total_blocks, total_wait_time,
                consecutive_successes, uptime_seconds, delay_changes_count
        """
        uptime = (datetime.now() - self._created_at).total_seconds()

        return {
            "current_delay": self._current_delay,
            "initial_delay": self._initial_delay,
            "min_delay": self._min_delay,
            "max_delay": self._max_delay,
            "total_requests": self._total_requests,
            "total_successes": self._total_successes,
            "total_errors": self._total_errors,
            "total_rate_limits": self._total_rate_limits,
            "total_blocks": self._total_blocks,
            "total_wait_time": round(self._total_wait_time, 2),
            "consecutive_successes": self._consecutive_successes,
            "uptime_seconds": round(uptime, 2),
            "delay_changes_count": len(self._delay_changes),
            "delay_changes": list(self._delay_changes),  # copy
        }

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def current_delay(self) -> float:
        """Current delay value in seconds."""
        return self._current_delay

    @property
    def consecutive_successes(self) -> int:
        """Number of consecutive successes since last error or delay change."""
        return self._consecutive_successes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_delay_change(self, old_delay: float, new_delay: float, reason: str):
        """Record and log a delay change event."""
        change_record = {
            "timestamp": datetime.now().isoformat(),
            "old_delay": old_delay,
            "new_delay": new_delay,
            "reason": reason,
        }
        self._delay_changes.append(change_record)

        logger.info(
            f"Rate limiter delay changed: {old_delay:.1f}s → {new_delay:.1f}s "
            f"(reason: {reason})"
        )
