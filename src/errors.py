"""
Exception hierarchy for the pipeline.

Classifies errors into three categories:
- RetryableError: Temporary errors that should be retried (429, timeout, network)
- SkippableError: Company-specific errors that should skip the company (invalid data, no results)
- CriticalError: Critical errors that stop the entire pipeline (402, DB corrupt)
"""


class PipelineError(Exception):
    """Base class for all pipeline errors."""

    def __init__(self, message, company_id=None, step=None):
        """Initialize PipelineError.

        Args:
            message: Error description
            company_id: Company ID associated with the error (optional)
            step: Pipeline step where the error occurred (optional)
        """
        super().__init__(message)
        self.message = message
        self.company_id = company_id
        self.step = step

    @property
    def category(self):
        """Return the error category string."""
        return "unknown"


class RetryableError(PipelineError):
    """Temporary error — should retry (429, timeout, network, transient failures)."""
    @property
    def category(self):
        return "retryable"


class SkippableError(PipelineError):
    """Company-specific error — skip company, continue batch (invalid data, no results)."""
    @property
    def category(self):
        return "skippable"


class CriticalError(PipelineError):
    """Critical error — stop entire pipeline (402 credits exhausted, DB corrupt)."""
    @property
    def category(self):
        return "critical"
