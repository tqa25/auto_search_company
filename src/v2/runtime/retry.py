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
        self.base_delay = 1.0  # seconds
        self.max_delay = 60.0  # seconds
        self.jitter_factor = 0.2  # ±20% jitter
        
    def execute(self, operation: Callable[[], T]) -> T:
        """
        Execute operation with retry logic.
        
        Args:
            operation: Callable that performs the API call. Should raise
                      RetryableError for transient failures, CriticalError/SkippableError
                      for non-retryable failures.
        
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
            try:
                result = operation()
                if attempt > 1:
                    logger.info(f"Operation succeeded on attempt {attempt}/{self.max_attempts}")
                return result
                
            except CriticalError as e:
                # Critical errors: stop immediately, no retry
                logger.error(f"Critical error on attempt {attempt}: {e}. Aborting.")
                raise
                
            except SkippableError as e:
                # Skippable errors: stop immediately, no retry
                logger.warning(f"Skippable error on attempt {attempt}: {e}. Not retrying.")
                raise
                
            except RetryableError as e:
                # Retryable errors: retry if attempts remain
                last_error = e
                if attempt < self.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Retryable error on attempt {attempt}/{self.max_attempts}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Max attempts ({self.max_attempts}) exhausted. Last error: {e}")
                    raise RetryableError(f"Max attempts ({self.max_attempts}) exhausted: {e}") from e
                    
            except Exception as e:
                # Unknown exceptions: treat as retryable by default
                last_error = e
                if attempt < self.max_attempts:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Unexpected error on attempt {attempt}/{self.max_attempts}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Max attempts ({self.max_attempts}) exhausted. Last error: {e}")
                    raise RetryableError(f"Max attempts ({self.max_attempts}) exhausted: {e}") from e
        
        # Should not reach here, but safety net
        raise RetryableError(f"Max attempts ({self.max_attempts}) exhausted: {last_error}")
    
    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff with jitter.
        
        attempt=1 (first retry) → ~1s
        attempt=2 (second retry) → ~2s
        attempt=3 (third retry) → ~4s
        etc.
        
        Jitter: ±20% to prevent thundering herd.
        """
        # Exponential backoff: base_delay * 2^(attempt-1)
        delay = self.base_delay * (2 ** (attempt - 1))
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter: ±jitter_factor
        jitter = delay * self.jitter_factor * (2 * random.random() - 1)
        delay = max(0.1, delay + jitter)  # minimum 0.1s
        
        return delay


def classify_error(
    status_code: int,
    message: str = "",
    original_exception: Optional[Exception] = None
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
    retryable_codes = {429, 500, 502, 503, 504}
    if status_code in retryable_codes:
        return RetryableError(f"HTTP {status_code}: {message}")
    
    # Network-level retryable errors
    if original_exception is not None:
        import requests
        if isinstance(original_exception, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return RetryableError(f"Network error: {original_exception}")
    
    # Transient error messages (even if status code unclear)
    transient_markers = [
        "unavailable", "experiencing high demand", "service unavailable",
        "temporarily unavailable", "try again later", "rate limit"
    ]
    if any(marker in msg_lower for marker in transient_markers):
        return RetryableError(f"Transient error: {message}")
    
    # Skippable errors — company-specific, don't retry, continue batch
    skippable_codes = {400, 403, 404, 410, 422}
    if status_code in skippable_codes:
        return SkippableError(f"HTTP {status_code}: {message}")
    
    # Unknown status codes: default to skippable (safer than infinite retry)
    if status_code >= 400:
        return SkippableError(f"HTTP {status_code}: {message}")
    
    # Unknown exception without status code: retryable by default
    return RetryableError(f"Unknown error: {message}")


def create_retry_executor(config: Config) -> RetryExecutor:
    """Factory function to create a RetryExecutor from config."""
    return RetryExecutor(config)