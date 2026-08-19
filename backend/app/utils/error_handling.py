"""Error handling and recovery for Industrial Knowledge Brain API."""

import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

# HTTP Status Code Mapping
HTTP_STATUS_CODES = {
    400: "Bad Request - Invalid input",
    401: "Unauthorized - Authentication required",
    403: "Forbidden - Access denied",
    404: "Not Found - Resource does not exist",
    409: "Conflict - Resource conflict",
    429: "Rate Limited - Too many requests",
    500: "Internal Server Error",
    502: "Bad Gateway - Service unavailable",
    503: "Service Unavailable - Please try again later",
}

class APIError(Exception):
    """Base API error."""
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(APIError):
    """Validation error (400)."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 400, details)

class AuthenticationError(APIError):
    """Authentication error (401)."""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, 401)

class NotFoundError(APIError):
    """Resource not found (404)."""
    def __init__(self, resource: str):
        super().__init__(f"{resource} not found", 404)

class RateLimitError(APIError):
    """Rate limit exceeded (429)."""
    def __init__(self, retry_after: int = 60):
        super().__init__(f"Rate limited. Retry after {retry_after}s", 429)

class ServiceError(APIError):
    """Service error (5xx)."""
    def __init__(self, message: str = "Service error", status_code: int = 500):
        super().__init__(message, status_code)

def handle_errors(func: Callable) -> Callable:
    """Decorator for API error handling."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            logger.warning(f"Validation error in {func.__name__}: {e.message}")
            return {"error": e.message, "details": e.details}, e.status_code
        except AuthenticationError as e:
            logger.warning(f"Authentication error: {e.message}")
            return {"error": e.message}, e.status_code
        except NotFoundError as e:
            logger.info(f"Resource not found in {func.__name__}: {e.message}")
            return {"error": e.message}, e.status_code
        except RateLimitError as e:
            logger.warning(f"Rate limited: {e.message}")
            return {"error": e.message}, e.status_code
        except ServiceError as e:
            logger.error(f"Service error in {func.__name__}: {e.message}")
            return {"error": e.message}, e.status_code
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            return {"error": "Internal server error"}, 500
    return wrapper

def validate_input(schema: dict) -> Callable:
    """Decorator for input validation."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Extract request data
            from flask import request
            data = request.get_json() or {}
            
            # Validate required fields
            errors = {}
            for field, rules in schema.items():
                if rules.get("required", False) and field not in data:
                    errors[field] = f"{field} is required"
                elif field in data:
                    value = data[field]
                    # Type check
                    if "type" in rules and not isinstance(value, rules["type"]):
                        errors[field] = f"{field} must be {rules['type'].__name__}"
                    # Length check
                    if "min_length" in rules and len(str(value)) < rules["min_length"]:
                        errors[field] = f"{field} must be at least {rules['min_length']} characters"
                    if "max_length" in rules and len(str(value)) > rules["max_length"]:
                        errors[field] = f"{field} must not exceed {rules['max_length']} characters"
            
            if errors:
                raise ValidationError("Input validation failed", errors)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def retry_on_failure(max_attempts: int = 3, backoff_factor: float = 2.0) -> Callable:
    """Decorator for retry logic with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import time
            attempt = 0
            delay = 1.0
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except (ServiceError, RateLimitError) as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(f"Max retries exceeded for {func.__name__}")
                        raise
                    logger.warning(f"Retry {attempt}/{max_attempts} for {func.__name__} (delay: {delay}s)")
                    time.sleep(delay)
                    delay *= backoff_factor
            
            return None
        return wrapper
    return decorator

def sanitize_response(func: Callable) -> Callable:
    """Decorator to sanitize sensitive data from responses."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        response = func(*args, **kwargs)
        
        # Remove sensitive fields
        if isinstance(response, dict):
            sensitive_fields = ["password", "api_key", "secret", "token"]
            for field in sensitive_fields:
                if field in response:
                    del response[field]
        
        return response
    return wrapper

def log_audit(action: str) -> Callable:
    """Decorator for audit logging."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            from flask import request, g
            user_id = g.get("user_id", "unknown")
            timestamp = __import__("datetime").datetime.now().isoformat()
            
            logger.info(f"AUDIT: {action} | User: {user_id} | Time: {timestamp}")
            
            result = func(*args, **kwargs)
            
            logger.info(f"AUDIT: {action} completed successfully")
            return result
        return wrapper
    return decorator
