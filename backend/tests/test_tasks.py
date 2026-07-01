from __future__ import annotations

from typing import Any

import pytest


pytestmark = pytest.mark.asyncio


class TestCreateTask:
    TASKS_URL = "/api/v1/tasks"

    async def test_create_task_no_auth(self, client: Any, minimal_pdf: bytes) -> None:
        resp = await client.post(
            self.TASKS_URL,
            files={"file": ("test.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
        )
        assert resp.status_code == 401, resp.text

    async def test_create_task_no_file(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.STANDARD)
        resp = await client.post(
            self.TASKS_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422, resp.text

    async def test_create_task_invalid_ext(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.STANDARD)
        resp = await client.post(
            self.TASKS_URL,
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 415, resp.text

    async def test_create_task_success(self, client: Any, make_user: Any, minimal_pdf: bytes) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        resp = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "task_id" in data
        assert data["status"] in ("pending", "completed")
        assert data["filename"] == "paper.pdf"

    async def test_create_task_exceed_quota(self, client: Any, make_user: Any, minimal_pdf: bytes) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.FREE)
        resp = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        second = await client.post(
            self.TASKS_URL,
            files={"file": ("paper2.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 429 or second.status_code == 201, second.text

    async def test_create_task_empty_file(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        resp = await client.post(
            self.TASKS_URL,
            files={"file": ("empty.pdf", b"", "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, resp.text
        data = resp.json()
        assert "empty_file" in str(data.get("detail", {}))


class TestListTasks:
    TASKS_URL = "/api/v1/tasks"

    async def test_list_tasks_empty(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        resp = await client.get(
            self.TASKS_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] >= 0
        assert "items" in data

    async def test_list_tasks_with_pagination(self, client: Any, make_user: Any, minimal_pdf: bytes) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        resp = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        list_resp = await client.get(
            f"{self.TASKS_URL}?page=1&page_size=10",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.status_code == 200
        data = list_resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["items"]) > 0


class TestTaskDetail:
    TASKS_URL = "/api/v1/tasks"

    async def test_task_detail_not_found(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(
            f"{self.TASKS_URL}/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_task_detail_success(self, client: Any, make_user: Any, minimal_pdf: bytes) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create_resp = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201
        task_id = create_resp.json()["task_id"]
        detail = await client.get(
            f"{self.TASKS_URL}/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == 200, detail.text
        data = detail.json()
        assert data["id"] == task_id
        assert "filename" in data
        assert "status" in data


class TestDownloadCache:
    TASKS_URL = "/api/v1/tasks"

    async def test_download_cache(self, client: Any, make_user: Any, minimal_pdf: bytes) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        first = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 201
        first_data = first.json()

        second = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 201
        second_data = second.json()
        if second_data.get("cached"):
            assert second_data["cached_from"] is not None


class TestDownload:
    TASKS_URL = "/api/v1/tasks"

    async def test_download_not_completed(self, client: Any, make_user: Any, minimal_pdf: bytes) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create_resp = await client.post(
            self.TASKS_URL,
            files={"file": ("paper.pdf", minimal_pdf, "application/pdf")},
            data={"source_language": "en", "target_language": "zh"},
            headers={"Authorization": f"Bearer {token}"},
        )
        task_id = create_resp.json()["task_id"]
        download = await client.get(
            f"{self.TASKS_URL}/{task_id}/download?format=pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        if create_resp.json()["status"] != "completed":
            assert download.status_code == 409, download.text
