from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GlossaryTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(..., min_length=1, max_length=255)
    translation: str = Field(..., min_length=1, max_length=255)
    context: str | None = Field(default=None, max_length=512)


class GlossaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    domain: str = Field(default="general", max_length=32)
    terms: list[GlossaryTerm] = Field(..., min_length=1, max_length=10000)
    is_active: bool = Field(default=True)


class GlossaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None = None
    name: str
    description: str | None = None
    domain: str = "general"
    term_count: int = 0
    is_active: bool = True
    is_builtin: bool = False
    is_system: bool = False
    created_at: datetime
    updated_at: datetime


class GlossaryDetailResponse(GlossaryResponse):
    terms: list[GlossaryTerm] = Field(default_factory=list)


class GlossaryUploadResponse(BaseModel):
    glossary_id: str
    term_count: int
    skipped: int = 0
    warnings: list[str] = Field(default_factory=list)


class GlossaryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    terms: list[GlossaryTerm] | None = Field(default=None, min_length=1, max_length=10000)
    is_active: bool | None = None


class GlossaryCsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    domain: str = Field(default="general", max_length=32)
    terms: list[GlossaryTerm] = Field(..., min_length=1, max_length=10000)
