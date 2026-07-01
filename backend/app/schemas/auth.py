from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{6,14}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str = Field(..., min_length=3, max_length=255, description="手机号或邮箱")
    password: str = Field(..., min_length=8, max_length=128)
    code: str = Field(..., min_length=4, max_length=8, description="验证码")
    account_type: Literal["phone", "email"] = Field(...)
    nickname: str | None = Field(default=None, max_length=64)

    @field_validator("account")
    @classmethod
    def _validate_account(cls, value: str) -> str:
        if _PHONE_PATTERN.match(value) or _EMAIL_PATTERN.match(value):
            return value
        raise ValueError("account must be a valid phone number or email")

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("password must contain both letters and digits")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)
    account_type: Literal["phone", "email", "auto"] = Field(default="auto")


class SendCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str = Field(..., min_length=3, max_length=255)
    account_type: Literal["phone", "email"] = Field(...)
    purpose: Literal["register", "login", "reset"] = Field(default="register")

    @field_validator("account")
    @classmethod
    def _validate_account(cls, value: str) -> str:
        if _PHONE_PATTERN.match(value) or _EMAIL_PATTERN.match(value):
            return value
        raise ValueError("account must be a valid phone number or email")


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="过期秒数")
    user_id: str | None = None
