from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class PageMeta(ApiModel):
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool


class Page(ApiModel, Generic[T]):
    items: list[T]
    meta: PageMeta


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: Any | None = None
    retryable: bool = False


class ErrorResponse(ApiModel):
    error: ErrorDetail


class Acknowledgement(ApiModel):
    ok: bool = True
    message: str


class SignedUrl(ApiModel):
    url: str
    expires_at: datetime
    purpose: str
    note: str = Field(
        default=("Short-lived signed link bound to your user account. Uploaded documents are "
                 "never publicly accessible.")
    )


def page_meta(total: int, page: int, page_size: int) -> PageMeta:
    pages = max(1, -(-total // page_size)) if page_size else 1
    return PageMeta(
        total=total, page=page, page_size=page_size, pages=pages,
        has_next=page < pages, has_previous=page > 1,
    )
