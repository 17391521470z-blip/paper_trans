from __future__ import annotations

from typing import Any

import pytest


pytestmark = pytest.mark.asyncio


class TestStorageService:
    async def test_local_storage_put_and_get(self, tmp_path: Any) -> None:
        from app.services.storage_service import LocalStorage

        upload_root = tmp_path / "uploads"
        download_root = tmp_path / "downloads"
        storage = LocalStorage(
            upload_root=str(upload_root),
            download_root=str(download_root),
            signed_url_expire=3600,
        )
        result = await storage.put_object(
            "uploads/test/hello.txt",
            b"hello world",
            content_type="text/plain",
        )
        assert result.key == "uploads/test/hello.txt"
        assert result.size == 11
        assert await storage.exists("uploads/test/hello.txt") is True

        data = await storage.get_object("uploads/test/hello.txt")
        assert data == b"hello world"

    async def test_local_storage_signed_url(self, tmp_path: Any) -> None:
        from app.services.storage_service import LocalStorage

        storage = LocalStorage(
            upload_root=str(tmp_path / "uploads"),
            download_root=str(tmp_path / "downloads"),
            signed_url_expire=3600,
        )
        await storage.put_object("uploads/test/file.pdf", b"%PDF-data")
        url = await storage.generate_signed_url("uploads/test/file.pdf")
        assert url is not None
        assert "token=" in url
        assert "exp=" in url

    async def test_local_storage_delete(self, tmp_path: Any) -> None:
        from app.services.storage_service import LocalStorage

        storage = LocalStorage(
            upload_root=str(tmp_path / "uploads"),
            download_root=str(tmp_path / "downloads"),
        )
        await storage.put_object("uploads/test/tmp.txt", b"delete me")
        assert await storage.exists("uploads/test/tmp.txt") is True
        deleted = await storage.delete("uploads/test/tmp.txt")
        assert deleted is True
        assert await storage.exists("uploads/test/tmp.txt") is False

    async def test_local_storage_delete_nonexistent(self, tmp_path: Any) -> None:
        from app.services.storage_service import LocalStorage

        storage = LocalStorage(
            upload_root=str(tmp_path / "uploads"),
            download_root=str(tmp_path / "downloads"),
        )
        deleted = await storage.delete("uploads/test/nonexistent.txt")
        assert deleted is False


class TestLlmService:
    def test_compute_cost_deepseek(self) -> None:
        from app.services.llm_service import compute_cost

        cost = compute_cost("deepseek", prompt_tokens=1000, completion_tokens=500)
        assert cost.service == "deepseek"
        assert cost.prompt_cost_cny > 0
        assert cost.completion_cost_cny > 0
        assert cost.total_cost_cny > 0

    def test_compute_cost_glm(self) -> None:
        from app.services.llm_service import compute_cost

        cost = compute_cost("glm", prompt_tokens=2000, completion_tokens=1000)
        assert cost.service == "glm"
        assert cost.total_cost_cny > 0

    def test_compute_cost_zero_tokens(self) -> None:
        from app.services.llm_service import compute_cost

        cost = compute_cost("deepseek", prompt_tokens=0, completion_tokens=0)
        assert cost.total_cost_cny == 0.0

    def test_lookup_model_price(self) -> None:
        from app.services.llm_service import lookup_model_price

        price = lookup_model_price("deepseek-chat")
        assert price is not None
        prompt_rate, completion_rate = price
        assert prompt_rate > 0
        assert completion_rate > 0

    def test_lookup_model_price_unknown(self) -> None:
        from app.services.llm_service import lookup_model_price

        price = lookup_model_price("nonexistent-model-v42")
        assert price is None

    def test_estimate_tokens(self) -> None:
        from app.services.llm_service import estimate_tokens

        assert estimate_tokens("") == 0
        assert estimate_tokens("hello") == 2
        assert estimate_tokens("a" * 100) == 25


class TestStructureService:
    def test_should_translate_section(self) -> None:
        from app.services.structure_service import should_translate_section

        assert should_translate_section("Introduction") is True
        assert should_translate_section("Methods") is True
        assert should_translate_section("References") is False
        assert should_translate_section("Bibliography") is False
        assert should_translate_section("Acknowledgments") is False
        assert should_translate_section("") is True

    def test_detect_sections_heuristic(self) -> None:
        from app.services.structure_service import detect_sections_heuristic

        text = (
            "Abstract\nThis is a paper about AI.\n"
            "Introduction\nWe introduce a new method.\n"
            "References\n[1] Someone et al.\n"
        )
        sections = detect_sections_heuristic(text)
        assert "Abstract" in sections
        assert "Introduction" in sections
        assert "References" in sections or "Reference" in sections

    def test_build_skip_references_prompt(self) -> None:
        from app.services.structure_service import build_skip_references_prompt

        prompt = build_skip_references_prompt(skip=True)
        assert "References" in prompt
        assert "Bibliography" in prompt

        empty = build_skip_references_prompt(skip=False)
        assert empty == ""

    def test_inject_glossary_into_prompt(self) -> None:
        from app.services.structure_service import inject_glossary_into_prompt

        glossary = [
            {"term": "transformer", "translation": "Transformer 模型"},
            {"term": "embedding", "translation": "嵌入", "context": "表示学习"},
        ]
        prompt = inject_glossary_into_prompt(glossary)
        assert "transformer" in prompt
        assert "Transformer 模型" in prompt
        assert "embedding" in prompt
        assert "表示学习" in prompt

        empty = inject_glossary_into_prompt([])
        assert empty == ""


class TestMarkdownService:
    async def test_convert_pdf_to_markdown_no_pandoc(self, minimal_pdf: bytes, tmp_path: Any) -> None:
        from app.services.markdown_service import convert_pdf_to_markdown

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(minimal_pdf)
        result = await convert_pdf_to_markdown(str(pdf_path), use_pandoc=False)
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_extract_pages_text(self, minimal_pdf: bytes, tmp_path: Any) -> None:
        from app.services.markdown_service import extract_pages_text

        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(minimal_pdf)
        pages = await extract_pages_text(str(pdf_path))
        assert isinstance(pages, list)


class TestCostMonitor:
    async def test_record_llm_call(self, db_session: Any, make_user: Any) -> None:
        from app.models.task import Task, TaskStatus
        from app.services.cost_monitor_service import record_llm_call

        user, token = await make_user()
        task = Task(
            user_id=user.id,
            filename="test.pdf",
            file_hash="abc123",
            status=TaskStatus.PENDING,
        )
        db_session.add(task)
        await db_session.flush()

        await record_llm_call(
            db_session,
            task_id=task.id,
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=50,
            cost_cny=0.001,
        )
        await db_session.refresh(task)
        assert task.prompt_tokens == 100
        assert task.completion_tokens == 50
        assert float(task.cost_cny or 0) > 0

    async def test_record_llm_call_invalid_task_id(self, db_session: Any) -> None:
        from app.services.cost_monitor_service import record_llm_call

        await record_llm_call(
            db_session,
            task_id="not-a-uuid",
            model="deepseek-chat",
            prompt_tokens=100,
            completion_tokens=50,
            cost_cny=0.001,
        )

    async def test_get_daily_cost_empty(self, db_session: Any) -> None:
        from app.services.cost_monitor_service import get_daily_cost

        summary = await get_daily_cost(db_session)
        assert summary.total_cost_cny == 0
        assert summary.call_count == 0


class TestTaskService:
    def test_validate_pdf_valid(self, minimal_pdf: bytes) -> None:
        from app.services.task_service import validate_pdf

        result = validate_pdf(minimal_pdf)
        assert result.is_valid is True
        assert result.page_count >= 0

    def test_validate_pdf_empty(self) -> None:
        from app.services.task_service import validate_pdf

        result = validate_pdf(b"")
        assert result.is_valid is False
        assert result.error == "empty file"

    def test_validate_pdf_no_magic(self) -> None:
        from app.services.task_service import validate_pdf

        result = validate_pdf(b"not a pdf at all")
        assert result.is_valid is False
        assert "magic" in (result.error or "").lower()

    def test_compute_pdf_hash(self, minimal_pdf: bytes) -> None:
        from app.services.task_service import compute_pdf_hash

        h = compute_pdf_hash(minimal_pdf)
        assert isinstance(h, str)
        assert len(h) == 64

        h2 = compute_pdf_hash(b"different data")
        assert h != h2

    def test_compute_pdf_hash_empty(self) -> None:
        from app.services.task_service import compute_pdf_hash

        with pytest.raises(ValueError):
            compute_pdf_hash(b"")

    def test_build_object_key(self) -> None:
        from app.services.task_service import build_object_key

        import uuid

        uid = uuid.uuid4()
        key = build_object_key(uid, "my paper.pdf", "abcdef123456")
        assert uid.hex[:12] in key
        assert "my_paper.pdf" in key or "my paper.pdf" in key


class TestQuotaService:
    def test_check_quota_allowed(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.quota_service import check_quota

        result = check_quota(
            tier=QuotaTier.STANDARD,
            used_pages=0,
            monthly_pages=200,
            used_daily_pages=0,
            daily_pages=50,
            requested_pages=1,
        )
        assert result.allowed is True
        assert result.remaining_monthly == 200
        assert result.remaining_daily == 50

    def test_check_quota_monthly_exceeded(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.quota_service import check_quota

        result = check_quota(
            tier=QuotaTier.FREE,
            used_pages=30,
            monthly_pages=30,
            used_daily_pages=0,
            daily_pages=5,
            requested_pages=1,
        )
        assert result.allowed is False
        assert result.reason == "monthly_quota_exceeded"

    def test_check_quota_daily_exceeded(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.quota_service import check_quota

        result = check_quota(
            tier=QuotaTier.FREE,
            used_pages=0,
            monthly_pages=30,
            used_daily_pages=5,
            daily_pages=5,
            requested_pages=1,
        )
        assert result.allowed is False
        assert result.reason == "daily_quota_exceeded"

    def test_consume_quota(self) -> None:
        from app.services.quota_service import consume_quota

        import uuid

        result = consume_quota(
            user_id=uuid.uuid4(),
            used_pages=5,
            used_daily_pages=2,
            requested_pages=1,
        )
        assert result.consumed is True
        assert result.new_used_pages == 6
        assert result.new_used_daily_pages == 3

    def test_consume_quota_invalid(self) -> None:
        from app.services.quota_service import consume_quota

        import uuid

        result = consume_quota(
            user_id=uuid.uuid4(),
            used_pages=5,
            used_daily_pages=2,
            requested_pages=0,
        )
        assert result.consumed is False

    def test_tier_default_pages(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.quota_service import tier_default_pages

        monthly, daily = tier_default_pages(QuotaTier.FREE)
        assert monthly == 30
        assert daily == 5

        monthly, daily = tier_default_pages(QuotaTier.STANDARD)
        assert monthly == 200
        assert daily == 50

        monthly, daily = tier_default_pages(QuotaTier.PRO)
        assert monthly == 800
        assert daily == 150
