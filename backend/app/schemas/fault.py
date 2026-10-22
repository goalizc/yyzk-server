"""故障知识库 schema（契约 §4）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import AppDateTime

# 附件与步骤配图只允许本站上传目录或 http(s) 链接：
# 运营录入视为不可信输入，javascript:/data: 之类会在前端渲染时变成 XSS
_ALLOWED_MEDIA_PREFIXES = ("/uploads/", "http://", "https://")


def _validate_media_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith(_ALLOWED_MEDIA_PREFIXES):
        raise ValueError("图片/附件地址必须是 /uploads/ 或 http(s) 链接")
    return value


class SolutionStep(BaseModel):
    step: int = Field(ge=1, examples=[1])
    text: str = Field(min_length=1, examples=["检查电源适配器指示灯是否亮起"])
    image_url: str | None = None

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("步骤内容不能为空")
        return value

    @field_validator("image_url")
    @classmethod
    def _check_image_url(cls, value: str | None) -> str | None:
        return _validate_media_url(value)


class AttachmentMeta(BaseModel):
    name: str = Field(max_length=200)
    url: str = Field(max_length=500)
    size: int = Field(ge=0)

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        checked = _validate_media_url(value)
        if checked is None:
            raise ValueError("附件地址不能为空")
        return checked


def normalize_steps(steps: list[SolutionStep]) -> list[SolutionStep]:
    """按 step 去重（保留首个）并升序 —— 契约 §4 的入库要求。"""
    by_step: dict[int, SolutionStep] = {}
    for step in steps:
        by_step.setdefault(step.step, step)
    return [by_step[key] for key in sorted(by_step)]


class FaultListItem(BaseModel):
    """客户侧列表项（不带大字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    symptom: str | None = None
    view_count: int


class FaultDetail(BaseModel):
    """客户侧详情。query_log_id 必须由前端保存，反馈时回传。"""

    id: int
    product_id: int
    part_id: int
    product_name: str
    part_name: str
    title: str
    symptom: str | None = None
    root_cause: str | None = None
    solution_steps: list[dict[str, Any]] = []
    required_tools: str | None = None
    needs_professional: bool = False
    attachment_urls: list[dict[str, Any]] = []
    view_count: int
    resolved_count: int
    query_log_id: int


class FaultAdminItem(BaseModel):
    """后台列表项：不含 solution_steps（契约明确要求）。"""

    id: int
    product_id: int
    product_name: str
    part_id: int
    part_name: str
    title: str
    symptom: str | None = None
    needs_professional: bool
    is_published: bool
    view_count: int
    resolved_count: int
    attachment_count: int
    created_at: AppDateTime
    updated_at: AppDateTime


class FaultAdminDetail(BaseModel):
    """后台编辑回显：与公开详情不同构，不含 query_log_id。"""

    id: int
    product_id: int
    product_name: str | None = None
    part_id: int
    part_name: str | None = None
    title: str
    symptom: str | None = None
    root_cause: str | None = None
    solution_steps: list[dict[str, Any]] = []
    required_tools: str | None = None
    needs_professional: bool = False
    attachment_urls: list[dict[str, Any]] = []
    is_published: bool = True
    created_by: int | None = None
    created_at: AppDateTime
    updated_at: AppDateTime
    view_count: int
    resolved_count: int


class FaultCreate(BaseModel):
    product_id: int
    part_id: int
    title: str = Field(max_length=200, examples=["开机无反应"])
    symptom: str | None = None
    root_cause: str | None = None
    solution_steps: list[SolutionStep] = []
    required_tools: str | None = Field(default=None, max_length=200)
    needs_professional: bool = False
    attachment_urls: list[AttachmentMeta] = []
    is_published: bool = True

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("故障标题不能为空")
        return value

    @field_validator("solution_steps")
    @classmethod
    def _normalize(cls, value: list[SolutionStep]) -> list[SolutionStep]:
        return normalize_steps(value)


class FaultUpdate(BaseModel):
    product_id: int | None = None
    part_id: int | None = None
    title: str | None = Field(default=None, max_length=200)
    symptom: str | None = None
    root_cause: str | None = None
    solution_steps: list[SolutionStep] | None = None
    required_tools: str | None = Field(default=None, max_length=200)
    needs_professional: bool | None = None
    attachment_urls: list[AttachmentMeta] | None = None
    is_published: bool | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("故障标题不能为空")
        return value

    @field_validator("solution_steps")
    @classmethod
    def _normalize(cls, value: list[SolutionStep] | None) -> list[SolutionStep] | None:
        return None if value is None else normalize_steps(value)


class FaultPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FaultAdminItem]


class FeedbackRequest(BaseModel):
    query_log_id: int
    resolved: bool


class FeedbackResponse(BaseModel):
    success: bool = True
    message: str = "感谢反馈"


class QueryLogCreate(BaseModel):
    product_id: int
    part_id: int
    raw_query: str | None = Field(default=None, max_length=100)

    @field_validator("raw_query")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class QueryLogCreated(BaseModel):
    id: int
