"""
Centralized Exceptions - Phase ε.1 Purification Pass
Error taxonomy and structured error handling.
"""

from typing import Dict, Any, Optional
from fastapi import HTTPException, status


class PesoEchoError(Exception):
    """Base exception for PesoEcho system."""
    
    def __init__(self, message: str, error_code: str = "UNKNOWN", details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class RateLimitError(PesoEchoError):
    """Rate limit exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "RATE_LIMIT", details)


class AuthError(PesoEchoError):
    """Authentication or authorization error."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "AUTH_ERROR", details)


class PolicyViolationError(PesoEchoError):
    """Policy violation (e.g., WebSocket connection limits)."""
    
    def __init__(self, message: str = "Policy violation", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "POLICY_VIOLATION", details)


class StaleDataError(PesoEchoError):
    """Data is stale or unavailable."""
    
    def __init__(self, message: str = "Data is stale", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "STALE_DATA", details)


class BudgetGuardError(PesoEchoError):
    """Budget guard triggered (drawdown limit exceeded)."""
    
    def __init__(self, message: str = "Budget guard triggered", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "BUDGET_GUARD", details)


class ValidationError(PesoEchoError):
    """Data validation error."""
    
    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VALIDATION_ERROR", details)


class NetworkError(PesoEchoError):
    """Network connectivity error."""
    
    def __init__(self, message: str = "Network error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "NETWORK_ERROR", details)


class OrderError(PesoEchoError):
    """Order execution error."""
    
    def __init__(self, message: str = "Order execution failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "ORDER_ERROR", details)


class ConfigurationError(PesoEchoError):
    """Configuration error."""
    
    def __init__(self, message: str = "Configuration error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CONFIG_ERROR", details)


# Error mapping to HTTP responses
ERROR_TO_HTTP_STATUS = {
    RateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
    AuthError: status.HTTP_401_UNAUTHORIZED,
    PolicyViolationError: status.HTTP_403_FORBIDDEN,
    StaleDataError: status.HTTP_503_SERVICE_UNAVAILABLE,
    BudgetGuardError: status.HTTP_403_FORBIDDEN,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    NetworkError: status.HTTP_503_SERVICE_UNAVAILABLE,
    OrderError: status.HTTP_400_BAD_REQUEST,
    ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def create_http_exception(error: PesoEchoError) -> HTTPException:
    """Convert PesoEchoError to HTTPException with proper status code."""
    status_code = ERROR_TO_HTTP_STATUS.get(type(error), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return HTTPException(
        status_code=status_code,
        detail={
            "error": error.error_code,
            "message": error.message,
            "details": error.details
        }
    )


def sanitize_error_message(message: str) -> str:
    """Sanitize error messages to prevent information leakage."""
    # Remove potential sensitive information
    sensitive_patterns = [
        "password", "secret", "key", "token", "private",
        "api_key", "access_token", "refresh_token"
    ]
    
    sanitized = message
    for pattern in sensitive_patterns:
        if pattern.lower() in sanitized.lower():
            sanitized = sanitized.replace(pattern, "***")
    
    return sanitized


def create_structured_error_response(error: Exception) -> Dict[str, Any]:
    """Create structured error response for logging and API responses."""
    if isinstance(error, PesoEchoError):
        return {
            "error_type": error.error_code,
            "message": sanitize_error_message(error.message),
            "details": error.details,
            "timestamp": None  # Will be filled by caller
        }
    else:
        return {
            "error_type": "UNKNOWN_ERROR",
            "message": sanitize_error_message(str(error)),
            "details": {},
            "timestamp": None
        }
