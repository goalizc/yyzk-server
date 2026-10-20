"""通用 schema：错误体、健康检查、分页与时间类型。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

from app.core.time import to_app_tz


class ErrorBody(BaseModel):
    """契约 §0.2 固定错误体，用于 OpenAPI 文档声明。"""

    detail: str = Field(description="面向用户的中文提示，可直接展示")
    code: str = Field(description="稳定机器码，前端按此分支处理")


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    db: str = Field(examples=["ok"])


class SuccessResponse(BaseModel):
    success: bool = True


# 输出始终带 +08:00，与契约的 ISO 8601 示例一致
AppDateTime = Annotated[
    datetime, PlainSerializer(lambda value: to_app_tz(value).isoformat(), return_type=str)
]


class UploadResult(BaseModel):
    url: str
    filename: str
    size: int
