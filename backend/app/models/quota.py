from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.guid import GUID


if TYPE_CHECKING:
    from app.models.user import User


class QuotaTier(str, enum.Enum):
    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"


class Quota(Base):
    __tablename__ = "quotas"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    tier: Mapped[QuotaTier] = mapped_column(
        Enum(QuotaTier, name="quota_tier"),
        default=QuotaTier.FREE,
        nullable=False,
    )
    monthly_pages: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    used_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_pages: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    used_daily_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    daily_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="quota")

    def __repr__(self) -> str:
        return f"<Quota user_id={self.user_id} tier={self.tier} used={self.used_pages}/{self.monthly_pages}>"


TIER_MONTHLY_PAGES: dict[QuotaTier, int] = {
    QuotaTier.FREE: 30,
    QuotaTier.STANDARD: 200,
    QuotaTier.PRO: 500,
}


def tier_default_pages(tier: QuotaTier) -> tuple[int, int]:
    pages = TIER_MONTHLY_PAGES.get(tier, 30)
    return pages, max(5, pages // 6)
