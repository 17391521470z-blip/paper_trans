from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., min_length=1, max_length=512)
    file_size: int = Field(..., ge=1, le=52428800)
    file_hash: str | None = Field(default=None, max_length=64)
    page_count: int | None = Field(default=None, ge=1, le=100)
    source_language: str = Field(default="en", min_length=2, max_length=16)
    target_language: str = Field(default="zh", min_length=2, max_length=16)
    llm_service: Literal["deepseek", "glm", "openai"] = Field(default="deepseek")
    glossary_id: str | None = Field(default=None, description="关联的术语库 ID")
    skip_references: bool = Field(default=True)
    detect_sections: bool = Field(default=True)
    output_formats: list[Literal["pdf", "markdown", "docx"]] = Field(
        default_factory=lambda: ["pdf"],
    )
    options: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    filename: str
    file_hash: str
    file_size: int = 0
    page_count: int = 0
    status: Literal["pending", "processing", "completed", "failed", "cancelled"]
    progress: int = Field(..., ge=0, le=100)
    source_language: str = "en"
    target_language: str = "zh"
    llm_service: str = "deepseek"
    glossary_id: str | None = None
    result_url: str | None = None
    result_md_url: str | None = None
    result_docx_url: str | None = None
    error_message: str | None = None
    cost_cny: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
