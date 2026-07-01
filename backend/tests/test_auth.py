from __future__ import annotations

from typing import Any

import pytest


pytestmark = pytest.mark.asyncio


class TestRegister:
    REGISTER_URL = "/api/v1/auth/register"

    async def test_register_success(self, client: Any, dev_code: str) -> None:
        payload = {
            "account": f"test-{__import__('uuid').uuid4().hex[:8]}@example.com",
            "password": "TestPass123",
            "code": dev_code,
            "account_type": "email",
        }
        resp = await client.post(self.REGISTER_URL, json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == payload["account"]
        assert data["user"]["is_active"] is True

    async def test_register_duplicate_phone(self, client: Any, dev_code: str) -> None:
        phone = f"+861380000{__import__('uuid').uuid4().hex[:4]}"
        payload = {
            "account": phone,
            "password": "TestPass123",
            "code": dev_code,
            "account_type": "phone",
        }
        resp1 = await client.post(self.REGISTER_URL, json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post(self.REGISTER_URL, json=payload)
        assert resp2.status_code == 409, resp2.text

    async def test_register_weak_password(self, client: Any, dev_code: str) -> None:
        payload = {
            "account": f"weak-{__import__('uuid').uuid4().hex[:8]}@example.com",
            "password": "short",  # less than 8
            "code": dev_code,
            "account_type": "email",
        }
        resp = await client.post(self.REGISTER_URL, json=payload)
        assert resp.status_code == 422, resp.text

    async def test_register_invalid_account(self, client: Any, dev_code: str) -> None:
        payload = {
            "account": "not-an-email-or-phone",
            "password": "TestPass123",
            "code": dev_code,
            "account_type": "email",
        }
        resp = await client.post(self.REGISTER_URL, json=payload)
        assert resp.status_code == 422, resp.text


class TestLogin:
    LOGIN_URL = "/api/v1/auth/login"
    REGISTER_URL = "/api/v1/auth/register"

    async def _register_user(self, client: Any, dev_code: str) -> dict[str, Any]:
        email = f"login-{__import__('uuid').uuid4().hex[:8]}@example.com"
        payload = {
            "account": email,
            "password": "TestPass123",
            "code": dev_code,
            "account_type": "email",
        }
        resp = await client.post(self.REGISTER_URL, json=payload)
        assert resp.status_code == 201
        return {"email": email, "password": "TestPass123"}

    async def test_login_success(self, client: Any, dev_code: str) -> None:
        creds = await self._register_user(client, dev_code)
        resp = await client.post(
            self.LOGIN_URL,
            json={
                "account": creds["email"],
                "password": creds["password"],
                "account_type": "email",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: Any, dev_code: str) -> None:
        creds = await self._register_user(client, dev_code)
        resp = await client.post(
            self.LOGIN_URL,
            json={
                "account": creds["email"],
                "password": "WrongPass999",
                "account_type": "email",
            },
        )
        assert resp.status_code == 401, resp.text

    async def test_login_nonexistent_user(self, client: Any) -> None:
        resp = await client.post(
            self.LOGIN_URL,
            json={
                "account": "nonexistent@example.com",
                "password": "TestPass123",
                "account_type": "email",
            },
        )
        assert resp.status_code == 401, resp.text


class TestCurrentUser:
    ME_URL = "/api/v1/users/me"

    async def test_get_current_user_with_token(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.FREE)
        resp = await client.get(
            self.ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == str(_user.id)
        assert data["is_active"] is True

    async def test_get_current_user_no_token(self, client: Any) -> None:
        resp = await client.get(self.ME_URL)
        assert resp.status_code == 401, resp.text

    async def test_get_current_user_invalid_token(self, client: Any) -> None:
        resp = await client.get(
            self.ME_URL,
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        assert resp.status_code == 401, resp.text

    async def test_get_current_user_expired_token(self, client: Any, monkeypatch: Any) -> None:
        from datetime import timedelta

        monkeypatch.setattr("app.core.config.get_settings().jwt_expire_minutes", -1)
        from app.core.security import create_access_token

        expired = create_access_token(
            {"sub": "00000000-0000-0000-0000-000000000000"},
            expires_delta=timedelta(minutes=-1),
        )
        resp = await client.get(
            self.ME_URL,
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401, resp.text


class TestQuota:
    QUOTA_URL = "/api/v1/quotas"

    async def test_get_quotas_after_register(self, client: Any, dev_code: str) -> None:
        email = f"quota-{__import__('uuid').uuid4().hex[:8]}@example.com"
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "account": email,
                "password": "TestPass123",
                "code": dev_code,
                "account_type": "email",
            },
        )
        assert reg_resp.status_code == 201
        token = reg_resp.json()["access_token"]
        resp = await client.get(
            self.QUOTA_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tier"] == "free"
        assert data["monthly_pages"] >= 30
        assert data["used_pages"] == 0

    async def test_quota_check_endpoint(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.STANDARD)
        resp = await client.get(
            "/api/v1/quotas/check?pages=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["allowed"] is True
        assert data["tier"] == "standard"
        assert data["requested_pages"] == 1


class TestSendCode:
    SEND_CODE_URL = "/api/v1/auth/send-code"

    async def test_send_code_dev(self, client: Any) -> None:
        resp = await client.post(
            self.SEND_CODE_URL,
            json={
                "account": f"+861380000{__import__('uuid').uuid4().hex[:4]}",
                "account_type": "phone",
                "purpose": "register",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dev_code"] == "123456"

    async def test_send_code_empty_account(self, client: Any) -> None:
        resp = await client.post(
            self.SEND_CODE_URL,
            json={
                "account": "",
                "account_type": "phone",
                "purpose": "register",
            },
        )
        assert resp.status_code == 422, resp.text


class TestChangePassword:
    CHANGE_PWD_URL = "/api/v1/auth/change-password"
    REGISTER_URL = "/api/v1/auth/register"

    async def test_change_password_success(self, client: Any, dev_code: str) -> None:
        email = f"chpwd-{__import__('uuid').uuid4().hex[:8]}@example.com"
        reg_resp = await client.post(
            self.REGISTER_URL,
            json={
                "account": email,
                "password": "OldPass123",
                "code": dev_code,
                "account_type": "email",
            },
        )
        assert reg_resp.status_code == 201
        token = reg_resp.json()["access_token"]
        resp = await client.post(
            self.CHANGE_PWD_URL,
            json={"old_password": "OldPass123", "new_password": "NewPass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data

    async def test_change_password_wrong_old(self, client: Any, dev_code: str) -> None:
        email = f"chpwd2-{__import__('uuid').uuid4().hex[:8]}@example.com"
        reg_resp = await client.post(
            self.REGISTER_URL,
            json={
                "account": email,
                "password": "OldPass123",
                "code": dev_code,
                "account_type": "email",
            },
        )
        token = reg_resp.json()["access_token"]
        resp = await client.post(
            self.CHANGE_PWD_URL,
            json={"old_password": "WrongOldPass", "new_password": "NewPass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, resp.text
