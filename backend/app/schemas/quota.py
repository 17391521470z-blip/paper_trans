from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QuotaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tier: Literal["free", "standard", "pro"]
    monthly_pages: int = Field(..., ge=0)
    used_pages: int = Field(..., ge=0)
    remaining_pages: int = Field(..., ge=0)
    daily_pages: int = Field(..., ge=0)
    used_daily_pages: int = Field(..., ge=0)
    remaining_daily_pages: int = Field(..., ge=0)
    reset_at: datetime | None = None
    daily_reset_at: datetime | None = None
