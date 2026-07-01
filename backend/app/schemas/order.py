from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Literal["free", "standard", "pro"]
    payment_method: Literal["wechat", "alipay"]
    quantity: int = Field(default=1, ge=1, le=12)
    client_ip: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    order_no: str
    tier: Literal["free", "standard", "pro"]
    amount_cny: float
    payment_method: Literal["wechat", "alipay"]
    status: Literal["pending", "paid", "refunded", "cancelled", "expired"]
    transaction_id: str | None = None
    qr_code_url: str | None = None
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaymentCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_no: str = Field(..., min_length=1, max_length=64)
    payment_method: Literal["wechat", "alipay"]
    transaction_id: str = Field(..., min_length=1, max_length=128)
    status: Literal["paid", "refunded", "failed"]
    amount_cny: float = Field(..., ge=0)
    paid_at: datetime | None = None
    signature: str | None = Field(default=None, max_length=1024)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
