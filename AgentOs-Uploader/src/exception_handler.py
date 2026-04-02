from fastapi import Request, status
from fastapi.responses import JSONResponse
import logging

from .exceptions import AppException, ErrorResponse

logger = logging.getLogger(__name__)


class UploaderException(AppException):
    """Uploader专用异常基类"""

    def __init__(self, message: str, code: str = "UPLOADER_ERROR", status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.code = code
        super().__init__(message, status_code)

class UploadException(UploaderException):
    """上传相关异常"""

    def __init__(self, message: str, code: str = "UPLOAD_ERROR"):
        super().__init__(message, code, status.HTTP_400_BAD_REQUEST)

class SessionException(UploaderException):
    """会话相关异常"""

    def __init__(self, message: str, code: str = "SESSION_ERROR"):
        super().__init__(message, code, status.HTTP_408_REQUEST_TIMEOUT)

class PlatformException(UploaderException):
    """平台相关异常"""

    def __init__(self, message: str, platform: str, code: str = "PLATFORM_ERROR"):
        self.platform = platform
        super().__init__(message, code, status.HTTP_400_BAD_REQUEST)

def handle_exception(func):
    """异常处理装饰器，统一处理函数中的异常"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except UploaderException as e:
            logger.warning(f"UploaderException: {e.message} (code: {e.code})")
            return JSONResponse(
                status_code=e.status_code,
                content=ErrorResponse(
                    code=e.code,
                    message=e.message
                ).to_dict()
            )
        except AppException as e:
            logger.warning(f"AppException: {e.message} (code: {e.status_code})")
            return JSONResponse(
                status_code=e.status_code,
                content=ErrorResponse(
                    code=f"APP_{e.status_code}",
                    message=e.message
                ).to_dict()
            )
        except Exception as e:
            logger.error(f"Unhandled Exception: {str(e)}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    code="INTERNAL_ERROR",
                    message="Internal server error"
                ).to_dict()
            )
    return wrapper

async def uploader_exception_handler(request: Request, exc: UploaderException):
    """Uploader专用异常处理器"""
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "UploaderException request_id=%s path=%s code=%s message=%s",
        request_id,
        request.url.path,
        exc.code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.code,
            message=exc.message,
            details={"request_id": request_id}
        ).to_dict()
    )

async def app_exception_handler(request: Request, exc: AppException):
    """通用应用异常处理器"""
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "AppException request_id=%s path=%s code=%s message=%s",
        request_id,
        request.url.path,
        exc.status_code,
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
    """全局异常处理器"""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unhandled Exception request_id=%s path=%s error=%s",
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