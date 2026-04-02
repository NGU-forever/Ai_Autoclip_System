from typing import Any, Dict

from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


class ErrorResponse:
    """标准化的错误响应格式"""

    def __init__(self, code: str, message: str, details: Dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class AppException(Exception):
    """Base exception for all application-level errors."""

    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=status.HTTP_404_NOT_FOUND)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Not enough permissions"):
        super().__init__(message, status_code=status.HTTP_403_FORBIDDEN)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Could not validate credentials"):
        super().__init__(message, status_code=status.HTTP_401_UNAUTHORIZED)


async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "AppException request_id=%s path=%s detail=%s",
        request_id,
        request.url.path,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=f"APP_{exc.status_code}",
            message=exc.message,
            details={"request_id": request_id}
        ).to_dict()
    )


async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled Exception request_id=%s path=%s err=%s",
        request_id,
        request.url.path,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            code="INTERNAL_ERROR",
            message="Internal server error",
            details={"request_id": request_id}
        ).to_dict()
    )
