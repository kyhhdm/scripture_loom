"""Unified error definitions for the application."""

from typing import Any, Optional


class MxSieveError(Exception):
    """Base exception for all MxSieve errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API response."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


class NotFoundError(MxSieveError):
    """Resource not found."""

    status_code = 404
    error_code = "NOT_FOUND"


class ValidationError(MxSieveError):
    """Request validation failed."""

    status_code = 400
    error_code = "VALIDATION_ERROR"


class AuthenticationError(MxSieveError):
    """Authentication failed."""

    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(MxSieveError):
    """Authorization failed - insufficient permissions."""

    status_code = 403
    error_code = "AUTHORIZATION_ERROR"


class RateLimitError(MxSieveError):
    """Rate limit exceeded."""

    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int = 60,
        details: Optional[dict[str, Any]] = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, details)


class TaskError(MxSieveError):
    """Task-related error."""

    status_code = 500
    error_code = "TASK_ERROR"


class TaskNotFoundError(NotFoundError):
    """Task not found."""

    error_code = "TASK_NOT_FOUND"


class TaskCancelledError(TaskError):
    """Task was cancelled."""

    status_code = 400
    error_code = "TASK_CANCELLED"


class TaskFailedError(TaskError):
    """Task execution failed."""

    error_code = "TASK_FAILED"


class ExternalServiceError(MxSieveError):
    """External service call failed."""

    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"


class LLMError(ExternalServiceError):
    """LLM API call failed."""

    error_code = "LLM_ERROR"


class LogsUnavailableError(MxSieveError):
    """Log access requested but no log file is configured (LOG_FILE unset)."""

    status_code = 503
    error_code = "LOGS_UNAVAILABLE"


class DuplicateExecutionSuppressedError(MxSieveError):
    """A worker picked up a task_id that another worker is already running.

    Raised by ProgressTrackingTask.before_start when the Redis lease on
    task_running:{task_id} is held by another live worker (broker
    redelivery — visibility timeout or connection loss). The task ends
    in FAILURE on this worker; task_service.get_status cross-checks the
    lease and continues to report the task as RUNNING so callers keep
    polling the live instance.
    """

    status_code = 409
    error_code = "DUPLICATE_EXECUTION_SUPPRESSED"
