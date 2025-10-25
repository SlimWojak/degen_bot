"""
Error Handler Middleware - Phase ε.1 Purification Pass
FastAPI exception handler for structured error responses.
"""

import logging
from typing import Union
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from backend.errors import (
    PesoEchoError, create_http_exception, create_structured_error_response,
    sanitize_error_message
)

logger = logging.getLogger(__name__)


async def peso_echo_exception_handler(request: Request, exc: PesoEchoError) -> JSONResponse:
    """Handle PesoEchoError exceptions with structured responses."""
    http_exc = create_http_exception(exc)
    
    # Log the error
    logger.error(f"PesoEchoError: {exc.error_code} - {exc.message}", extra={
        "error_code": exc.error_code,
        "details": exc.details,
        "path": str(request.url),
        "method": request.method
    })
    
    return JSONResponse(
        status_code=http_exc.status_code,
        content={
            "error": exc.error_code,
            "message": sanitize_error_message(exc.message),
            "details": exc.details,
            "path": str(request.url.path),
            "method": request.method
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTPException with structured responses."""
    logger.warning(f"HTTPException: {exc.status_code} - {exc.detail}", extra={
        "status_code": exc.status_code,
        "path": str(request.url),
        "method": request.method
    })
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": sanitize_error_message(str(exc.detail)),
            "details": {},
            "path": str(request.url.path),
            "method": request.method
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors with structured responses."""
    logger.warning(f"ValidationError: {exc.errors()}", extra={
        "errors": exc.errors(),
        "path": str(request.url),
        "method": request.method
    })
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {
                "validation_errors": exc.errors()
            },
            "path": str(request.url.path),
            "method": request.method
        }
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with structured responses."""
    logger.error(f"Unexpected error: {exc}", exc_info=True, extra={
        "path": str(request.url),
        "method": request.method
    })
    
    structured_error = create_structured_error_response(exc)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": structured_error["details"],
            "path": str(request.url.path),
            "method": request.method
        }
    )
