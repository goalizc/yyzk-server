"""Pydantic 请求/响应模型。"""

from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    UserOut,
)
from app.schemas.common import AppDateTime, ErrorBody, HealthResponse, SuccessResponse
from app.schemas.part import PartAdmin, PartCreate, PartPage, PartPublic, PartUpdate
from app.schemas.product import (
    ProductAdmin,
    ProductCreate,
    ProductPage,
    ProductPublic,
    ProductUpdate,
)

__all__ = [
    "AppDateTime",
    "ErrorBody",
    "HealthResponse",
    "LoginRequest",
    "LoginResponse",
    "PartAdmin",
    "PartCreate",
    "PartPage",
    "PartPublic",
    "PartUpdate",
    "PasswordChangeRequest",
    "PasswordChangeResponse",
    "ProductAdmin",
    "ProductCreate",
    "ProductPage",
    "ProductPublic",
    "ProductUpdate",
    "SuccessResponse",
    "UserOut",
]
