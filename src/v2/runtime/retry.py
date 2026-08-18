"""
Unified Retry Executor — single source of retry logic for all external API calls.

Consolidates six competing retry owners into one place:
- Attempt counting with exact semantics (MAX_ATTEMPTS = 1 initial + N retries)
- Exponential backoff with jitter
- Error classification: transient (retryable) vs permanent (futile)
- Structured logging of retry decisions
"""

import time
import random
import logging
from typing import Callable, TypeVar, Optional
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from src.config import Config
from src.errors import PipelineError, RetryableError, SkippableError, CriticalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryExecutor:
    """
    Executes an operation with unified retry policy.
    
    Usage:
        executor = RetryExecutor(config)
        result = executor.execute(lambda: api_call())
    """
    
    def __init__(self, config: Config):
        self.config = config
        # MAX_ATTEMPTS = 1 initial attempt + retries
        # e.g., MAX_ATTEMPTS=3 means 1 initial + 2 retries = 3 total calls
        self.max_attempts = getattr(config, "MAX_ATTEMPTS", config.MAX_RETRIES + 1)
        self.base_delay = 2.0  # seconds
        self.max_delay = 60.0  # seconds
        self.jitter_factor = 0.2  # ±20% jitter
        
    def execute(self, operation: Callable[[], T], should_stop: Optional[Callable[[], bool]] = None, context: Optional[dict] = None) -> T:
        """
        Execute operation with retry logic.

        Args:
            operation: Callable that performs the API call. Should raise
                      RetryableError for transient failures, CriticalError/SkippableError
                      for non-retryable failures.
            should_stop: Optional zero-arg callable returning True when shutdown requested.
                        Default None means never stop (preserves existing behavior).
            context: Optional dict with company_id, operation, provider for logging.

        Returns:
            The return value of operation() on success.

        Raises:
            RetryableError: If all attempts exhausted (transient failures)
            CriticalError: If critical error encountered (no retry)
            SkippableError: If skippable error encountered (no retry)
            PipelineError: Other pipeline errors (no retry)
        """
        attempt = 0
        last_error = None

        while attempt < self.max_attempts:
            attempt += 1
            _op_start = time.monotonic()
            try:
                result = operation()
                duration_ms = (time.monotonic() - _op_start) * 1000
                self._log_attempt("info", context, attempt, "success", "success", duration_ms=duration_ms)
                if attempt > 1:
                    logger.info(f"Operation succeeded on attempt {attempt}/{self.max_attempts}")
                return result

            except CriticalError as e:
                # Critical errors: stop immediately, no retry
                duration_ms = (time.monotonic() - _op_start) * 1000
                self._log_attempt("error", context, attempt, type(e).__name__, "stop", duration_ms=duration_ms)
                logger.error(f"Critical error on attempt {attempt}: {e}. Aborting.")
                raise

            except SkippableError as e:
                # Skippable errors: stop immediately, no retry
                duration_ms = (time.monotonic() - _op_start) * 1000
                self._log_attempt("warning", context, attempt, type(e).__name__, "fail", duration_ms=duration_ms)
                logger.warning(f"Skippable error on attempt {attempt}: {e}. Not retrying.")
                raise

            except RetryableError as e:
                # Retryable errors: retry if attempts remain
                duration_ms = (time.monotonic() - _op_start) * 1000
                last_error = e
                if attempt < self.max_attempts:
                    delay = self._calculate_delay(attempt, error=e)
                    self._log_attempt("warning", context, attempt, type(e).__name__, "retry", delay_seconds=delay, duration_ms=duration_ms)
                    logger.warning(
                        f"Retryable error on attempt {attempt}/{self.max_attempts}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    interrupted = self._interruptible_sleep(delay, should_stop)
                    if interrupted:
                        logger.warning(f"Shutdown requested during backoff (attempt {attempt}/{self.max_attempts}); aborting retry, not attempting again.")
                        raise last_error
                    continue
                else:
                    self._log_attempt("error", context, attempt, type(e).__name__, "fail", duration_ms=duration_ms)
                    logger.error(f"Max attempts ({self.max_attempts}) exhausted. Last error: {e}")
                    raise RetryableError(f"Max attempts ({self.max_attempts}) exhausted: {e}") from e

            except Exception as e:
                # Unknown exceptions: treat as retryable by default
                duration_ms = (time.monotonic() - _op_start) * 1000
                last_error = e
                if attempt < self.max_attempts:
                    delay = self._calculate_delay(attempt, error=e)
                    self._log_attempt("warning", context, attempt, type(e).__name__, "retry", delay_seconds=delay, duration_ms=duration_ms)
                    logger.warning(
                        f"Unexpected error on attempt {attempt}/{self.max_attempts}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    interrupted = self._interruptible_sleep(delay, should_stop)
                    if interrupted:
                        logger.warning(f"Shutdown requested during backoff (attempt {attempt}/{self.max_attempts}); aborting retry, not attempting again.")
                        raise last_error
                    continue
                else:
                    self._log_attempt("error", context, attempt, type(e).__name__, "fail", duration_ms=duration_ms)
                    logger.error(f"Max attempts ({self.max_attempts}) exhausted. Last error: {e}")
                    raise RetryableError(f"Max attempts ({self.max_attempts}) exhausted: {e}") from e

        # Should not reach here, but safety net
        raise RetryableError(f"Max attempts ({self.max_attempts}) exhausted: {last_error}")

    def _interruptible_sleep(self, delay: float, should_stop: Optional[Callable[[], bool]]) -> bool:
        """Sleep up to `delay` seconds, checking should_stop() periodically.
        Returns True if interrupted by should_stop, False if the full delay elapsed."""
        if should_stop is None:
            time.sleep(delay)
            return False
        poll_interval = 0.5
        elapsed = 0.0
        while elapsed < delay:
            if should_stop():
                return True
            step = min(poll_interval, delay - elapsed)
            time.sleep(step)
            elapsed += step
        return False

    def _log_attempt(self, level: str, context: Optional[dict], operation_attempt: int, status_or_error: str, decision: str, delay_seconds: float = 0.0, duration_ms: float = 0.0):
        """Log a structured attempt with context."""
        ctx = context or {}
        msg = (
            f"retry company_id={ctx.get('company_id', '-')} operation={ctx.get('operation', '-')} "
            f"provider={ctx.get('provider', '-')} attempt={operation_attempt} max_attempts={self.max_attempts} "
            f"status={status_or_error} decision={decision} delay_seconds={delay_seconds:.2f} duration_ms={duration_ms:.0f}"
        )
        getattr(logger, level)(msg)

    def _calculate_delay(self, attempt: int, error: Optional[Exception] = None) -> float:
        """
        Calculate exponential backoff with jitter.

        If error has a retry_after attribute (from HTTP Retry-After header),
        use that instead of exponential backoff.

        attempt=1 (first retry) → ~2s
        attempt=2 (second retry) → ~4s
        attempt=3 (third retry) → ~8s
        etc.

        Jitter: ±20% to prevent thundering herd.
        """
        # Honor Retry-After header if present
        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None:
            return max(0.0, float(retry_after))

        # Exponential backoff: base_delay * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))

        # Cap at max_delay
        delay = min(delay, self.max_delay)

        # Add jitter: ±jitter_factor
        jitter = delay * self.jitter_factor * (2 * random.random() - 1)
        delay = max(0.1, delay + jitter)  # minimum 0.1s

        return delay


def parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    """
    Parse an HTTP Retry-After header value into a number of seconds.

    Supports both forms per RFC 7231:
    - delta-seconds: a plain non-negative integer, e.g. "7"
    - HTTP-date: e.g. "Wed, 21 Oct 2026 07:28:00 GMT"

    Returns None if header_value is None/empty or cannot be parsed.
    Returned value is always >= 0 (clamped) if parsing succeeds.
    """
    if not header_value:
        return None

    # Try delta-seconds (integer) first
    try:
        value = float(header_value)
        return max(0.0, value)
    except ValueError:
        pass

    # Try HTTP-date format
    try:
        parsed_date = parsedate_to_datetime(header_value)
        now_utc = datetime.now(timezone.utc)
        delta_seconds = (parsed_date - now_utc).total_seconds()
        return max(0.0, delta_seconds)
    except (ValueError, TypeError):
        pass

    return None


def classify_error(
    status_code: int,
    message: str = "",
    original_exception: Optional[Exception] = None,
    retry_after_seconds: Optional[float] = None
) -> PipelineError:
    """
    Classify an HTTP error or exception into the pipeline error hierarchy.
    
    This is the single source of truth for error classification.
    Used by all modules to convert raw HTTP responses into structured errors.
    
    Args:
        status_code: HTTP status code (0 for network errors without status)
        message: Error message/description
        original_exception: The original exception if available
        
    Returns:
        Appropriate PipelineError subclass (RetryableError, SkippableError, CriticalError)
    """
    msg_lower = message.lower()
    
    # Critical errors — stop entire pipeline, no retry
    if status_code == 402 or "quota exceeded" in msg_lower or "credits exhausted" in msg_lower:
        return CriticalError(f"HTTP 402 / quota exhausted: {message}")
    
    if status_code == 401 or "unauthorized" in msg_lower or "invalid api key" in msg_lower:
        return CriticalError(f"HTTP 401 / unauthorized: {message}")
    
    # Database constraint errors (if detectable)
    if "constraint" in msg_lower or "unique" in msg_lower or "foreign key" in msg_lower:
        return CriticalError(f"Database constraint violation: {message}")
    
    # Retryable errors — transient, worth retrying
    retryable_codes = {408, 429, 500, 502, 503, 504}
    if status_code in retryable_codes:
        return RetryableError(f"HTTP {status_code}: {message}", retry_after=retry_after_seconds)
    
    # Network-level retryable errors
    if original_exception is not None:
        import requests
        if isinstance(original_exception, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return RetryableError(f"Network error: {original_exception}", retry_after=retry_after_seconds)
    
    # Transient error messages (even if status code unclear)
    transient_markers = [
        "unavailable", "experiencing high demand", "service unavailable",
        "temporarily unavailable", "try again later", "rate limit"
    ]
    if any(marker in msg_lower for marker in transient_markers):
        return RetryableError(f"Transient error: {message}", retry_after=retry_after_seconds)
    
    # Skippable errors — company-specific, don't retry, continue batch
    skippable_codes = {400, 403, 404, 410, 422}
    if status_code in skippable_codes:
        return SkippableError(f"HTTP {status_code}: {message}")
    
    # Unknown status codes: default to skippable (safer than infinite retry)
    if status_code >= 400:
        return SkippableError(f"HTTP {status_code}: {message}")
    
    # Unknown exception without status code: retryable by default
    return RetryableError(f"Unknown error: {message}", retry_after=retry_after_seconds)


def create_retry_executor(config: Config) -> RetryExecutor:
    """Factory function to create a RetryExecutor from config."""
    return RetryExecutor(config)