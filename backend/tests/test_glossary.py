from __future__ import annotations

import io
import uuid
from typing import Any

import pytest


pytestmark = pytest.mark.asyncio


def _csv_bytes(rows: list[tuple[str, str, str | None]]) -> bytes:
    buffer = io.StringIO()
    buffer.write("term,translation,context\n")
    for term, translation, context in rows:
        if context:
            buffer.write(f"{term},{translation},{context}\n")
        else:
            buffer.write(f"{term},{translation},\n")
    return buffer.getvalue().encode("utf-8-sig")


class TestParseCsv:
    def test_parses_basic_csv(self) -> None:
        from app.services.glossary_service import parse_csv

        raw = _csv_bytes(
            [
                ("transformer", "Transformer 模型", "深度学习"),
                ("fine-tuning", "微调", None),
                ("embedding", "嵌入", None),
            ]
        )
        result = parse_csv(raw)
        assert len(result.terms) == 3
        assert result.terms[0].term == "transformer"
        assert result.terms[0].translation == "Transformer 模型"
        assert result.terms[0].context == "深度学习"
        assert result.terms[1].context is None
        assert result.skipped == 0
        assert result.warnings == []

    def test_missing_columns_returns_warning(self) -> None:
        from app.services.glossary_service import parse_csv

        raw = b"foo,bar\n1,2\n"
        result = parse_csv(raw)
        assert result.terms == []
        assert any("missing required columns" in w for w in result.warnings)

    def test_empty_csv(self) -> None:
        from app.services.glossary_service import parse_csv

        result = parse_csv(b"")
        assert result.terms == []
        assert result.warnings

    def test_dedupes_duplicate_terms(self) -> None:
        from app.services.glossary_service import parse_csv

        raw = _csv_bytes(
            [
                ("transformer", "Transformer 模型", None),
                ("Transformer", "Transformer 模型", None),
                ("transformer", "Transformer", None),
            ]
        )
        result = parse_csv(raw)
        assert len(result.terms) == 1
        assert result.skipped == 2

    def test_skips_empty_rows(self) -> None:
        from app.services.glossary_service import parse_csv

        raw = (
            "term,translation,context\n"
            "transformer,Transformer,\n"
            ",,\n"
            "embedding,嵌入,表示\n"
            "\n"
        ).encode("utf-8")
        result = parse_csv(raw)
        assert len(result.terms) == 2
        assert result.skipped == 0

    def test_handles_alternate_headers(self) -> None:
        from app.services.glossary_service import parse_csv

        raw = (
            "source,target,note\n"
            "transformer,Transformer 模型,深度学习\n"
        ).encode("utf-8")
        result = parse_csv(raw)
        assert len(result.terms) == 1
        assert result.terms[0].term == "transformer"
        assert result.terms[0].translation == "Transformer 模型"

    def test_handles_gbk_encoding(self, unicode_csv: bytes) -> None:
        from app.services.glossary_service import parse_csv

        result = parse_csv(unicode_csv)
        assert len(result.terms) == 4
        assert any(t.term == "梯度下降" for t in result.terms)


class TestValidateGlossaryTerms:
    def test_valid_terms_no_errors(self) -> None:
        from app.services.glossary_service import validate_glossary_terms

        terms = [
            {"term": "transformer", "translation": "Transformer 模型", "context": None},
            {"term": "fine-tuning", "translation": "微调", "context": None},
        ]
        errors = validate_glossary_terms(terms)
        assert errors == []

    def test_empty_term_flagged(self) -> None:
        from app.services.glossary_service import validate_glossary_terms

        terms = [{"term": "  ", "translation": "微调", "context": None}]
        errors = validate_glossary_terms(terms)
        assert any("empty" in e for e in errors)

    def test_empty_translation_flagged(self) -> None:
        from app.services.glossary_service import validate_glossary_terms

        terms = [{"term": "fine-tuning", "translation": "", "context": None}]
        errors = validate_glossary_terms(terms)
        assert any("empty" in e for e in errors)

    def test_oversize_term_flagged(self) -> None:
        from app.services.glossary_service import (
            MAX_TERM_LENGTH,
            validate_glossary_terms,
        )

        long_term = "a" * (MAX_TERM_LENGTH + 10)
        terms = [{"term": long_term, "translation": "ok", "context": None}]
        errors = validate_glossary_terms(terms)
        assert any("exceeds" in e for e in errors)

    def test_too_many_terms_flagged(self) -> None:
        from app.services.glossary_service import validate_glossary_terms

        terms = [{"term": f"t{i}", "translation": f"译{i}", "context": None} for i in range(50)]
        errors = validate_glossary_terms(terms, max_terms=10)
        assert any("too many" in e for e in errors)


class TestQuota:
    def test_free_tier_blocked(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.glossary_service import check_quota_for_tier

        result = check_quota_for_tier(QuotaTier.FREE, current_count=0)
        assert result.allowed is False
        assert result.reason == "free_tier_cannot_create_glossary"

    def test_standard_tier_allows_first(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.glossary_service import check_quota_for_tier

        result = check_quota_for_tier(QuotaTier.STANDARD, current_count=0)
        assert result.allowed is True
        assert result.max_count == 1

    def test_standard_tier_blocks_second(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.glossary_service import check_quota_for_tier

        result = check_quota_for_tier(QuotaTier.STANDARD, current_count=1)
        assert result.allowed is False
        assert result.reason == "glossary_quota_exceeded"

    def test_pro_tier_allows_five(self) -> None:
        from app.models.quota import QuotaTier
        from app.services.glossary_service import check_quota_for_tier

        for i in range(5):
            assert check_quota_for_tier(QuotaTier.PRO, i).allowed is True
        assert check_quota_for_tier(QuotaTier.PRO, 5).allowed is False


class TestBuildGlossaryPrompt:
    def _build_glossary(self, name: str, terms: list[dict[str, Any]]):
        from app.models.glossary import Glossary

        return Glossary(
            id=uuid.uuid4(),
            user_id=None,
            name=name,
            terms=terms,
            term_count=len(terms),
            is_system=True,
            is_builtin=True,
            domain="cs_ai",
        )

    def test_prompt_contains_terms(self) -> None:
        from app.services.glossary_service import build_glossary_prompt

        glossary = self._build_glossary(
            "demo",
            [
                {"term": "transformer", "translation": "Transformer 模型", "context": None},
                {"term": "fine-tuning", "translation": "微调", "context": "训练"},
            ],
        )
        prompt = build_glossary_prompt(glossary)
        assert "transformer" in prompt
        assert "Transformer 模型" in prompt
        assert "fine-tuning" in prompt
        assert "微调" in prompt
        assert "请使用以下术语对照表" in prompt

    def test_prompt_handles_multiple_glossaries_dedup(self) -> None:
        from app.services.glossary_service import build_glossary_prompt

        g1 = self._build_glossary(
            "g1",
            [
                {"term": "transformer", "translation": "Transformer 模型", "context": None},
                {"term": "fine-tuning", "translation": "微调（用户）", "context": None},
            ],
        )
        g2 = self._build_glossary(
            "g2",
            [
                {"term": "fine-tuning", "translation": "微调（系统）", "context": None},
                {"term": "embedding", "translation": "嵌入", "context": None},
            ],
        )
        prompt = build_glossary_prompt([g1, g2])
        assert "fine-tuning" in prompt
        assert "embedding" in prompt
        assert prompt.count("fine-tuning") == 1

    def test_prompt_empty_for_empty_glossary(self) -> None:
        from app.services.glossary_service import build_glossary_prompt

        glossary = self._build_glossary("empty", [])
        assert build_glossary_prompt(glossary) == ""

    def test_prompt_truncates_at_max_terms(self) -> None:
        from app.services.glossary_service import build_glossary_prompt

        terms = [
            {"term": f"t{i}", "translation": f"译{i}", "context": None} for i in range(20)
        ]
        glossary = self._build_glossary("big", terms)
        prompt = build_glossary_prompt(glossary, max_terms=5)
        lines = [line for line in prompt.splitlines() if line.startswith("- ")]
        assert len(lines) == 5


class TestExportGlossaryCsv:
    def test_export_roundtrip(self) -> None:
        from app.services.glossary_service import export_glossary_csv, parse_csv

        from app.models.glossary import Glossary

        glossary = Glossary(
            id=uuid.uuid4(),
            user_id=None,
            name="test",
            terms=[
                {"term": "transformer", "translation": "Transformer 模型", "context": None},
                {"term": "fine-tuning", "translation": "微调", "context": "训练"},
            ],
            term_count=2,
            is_system=True,
        )
        body = export_glossary_csv(glossary)
        assert body.startswith(b"\xef\xbb\xbf") or body[:3] == b"\xef\xbb\xbf"
        parsed = parse_csv(body)
        assert len(parsed.terms) == 2
        assert parsed.terms[0].term == "transformer"
        assert parsed.terms[1].context == "训练"


class TestApiCrud:
    async def test_create_glossary_json_pro_user(
        self, client: Any, make_user: Any, sample_csv: bytes
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)

        payload = {
            "name": "我的术语库",
            "domain": "cs_ai",
            "terms": [
                {"term": "transformer", "translation": "Transformer 模型", "context": None},
                {"term": "fine-tuning", "translation": "微调", "context": "训练"},
            ],
        }
        resp = await client.post(
            "/api/v1/glossaries",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["term_count"] == 2
        assert data["is_system"] is False
        assert data["name"] == "我的术语库"

    async def test_create_glossary_csv_upload(
        self, client: Any, make_user: Any, sample_csv: bytes
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)

        resp = await client.post(
            "/api/v1/glossaries",
            files={"file": ("test.csv", sample_csv, "text/csv")},
            data={"name": "CSV 导入"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["term_count"] == 50

    async def test_free_tier_rejected(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.FREE)
        payload = {
            "name": "免费用户尝试",
            "terms": [{"term": "x", "translation": "y", "context": None}],
        }
        resp = await client.post(
            "/api/v1/glossaries",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text
        assert "升级" in resp.json()["detail"]["message"]

    async def test_standard_tier_second_glossary_rejected(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.STANDARD)
        payload = {
            "name": "首个",
            "terms": [{"term": "x", "translation": "y", "context": None}],
        }
        first = await client.post(
            "/api/v1/glossaries",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert first.status_code == 201

        second_payload = {
            "name": "第二个",
            "terms": [{"term": "z", "translation": "w", "context": None}],
        }
        second = await client.post(
            "/api/v1/glossaries",
            json=second_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert second.status_code == 403

    async def test_list_glossaries_includes_system(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        resp = await client.get(
            "/api/v1/glossaries",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any(g["is_system"] for g in data)

    async def test_get_detail(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "详情测试",
                "terms": [{"term": "t1", "translation": "译1", "context": None}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        gid = create.json()["id"]
        resp = await client.get(
            f"/api/v1/glossaries/{gid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["terms"][0]["term"] == "t1"

    async def test_patch_glossary(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "原名",
                "terms": [{"term": "t1", "translation": "译1", "context": None}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        gid = create.json()["id"]
        resp = await client.patch(
            f"/api/v1/glossaries/{gid}",
            json={"name": "新名"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "新名"

    async def test_delete_glossary(self, client: Any, make_user: Any) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "待删除",
                "terms": [{"term": "t1", "translation": "译1", "context": None}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        gid = create.json()["id"]
        resp = await client.delete(
            f"/api/v1/glossaries/{gid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204
        follow = await client.get(
            f"/api/v1/glossaries/{gid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert follow.status_code == 404

    async def test_export_glossary(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "导出测试",
                "terms": [{"term": "export", "translation": "导出", "context": None}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        gid = create.json()["id"]
        resp = await client.get(
            f"/api/v1/glossaries/{gid}/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        body = resp.content
        assert b"export" in body
        assert "导出".encode("utf-8") in body

    async def test_system_glossary_not_deletable(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        listing = await client.get(
            "/api/v1/glossaries",
            headers={"Authorization": f"Bearer {token}"},
        )
        sys_glossary = next(
            (g for g in listing.json() if g["is_system"]), None
        )
        assert sys_glossary is not None
        resp = await client.delete(
            f"/api/v1/glossaries/{sys_glossary['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    async def test_prompt_preview(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "prompt预览",
                "terms": [{"term": "transformer", "translation": "Transformer", "context": None}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        gid = create.json()["id"]
        resp = await client.get(
            f"/api/v1/glossaries/{gid}/prompt",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "transformer" in resp.json()["prompt"]

    async def test_glossary_with_terms_in_llm_prompt(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        create = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "LLM测试",
                "terms": [
                    {"term": "transformer", "translation": "Transformer 模型", "context": None},
                    {"term": "fine-tuning", "translation": "微调", "context": "训练"},
                ],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create.status_code == 201
        gid = create.json()["id"]
        resp = await client.get(
            f"/api/v1/glossaries/{gid}/prompt",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        prompt = resp.json()["prompt"]
        assert "transformer" in prompt
        assert "Transformer 模型" in prompt
        assert "fine-tuning" in prompt
        assert "微调" in prompt
        assert "术语对照表" in prompt

    async def test_glossary_quota_free_rejected(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.FREE)
        payload = {
            "name": "免费用户上传术语库",
            "terms": [{"term": "test", "translation": "测试", "context": None}],
        }
        resp = await client.post(
            "/api/v1/glossaries",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text
        detail = resp.json()["detail"]
        assert "升级" in detail["message"] or "free" in detail["code"].lower()

    async def test_glossary_csv_upload_large_file_rejected(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        large_csv = b"term,translation,context\n" + b"a,b,c\n" * 10000
        resp = await client.post(
            "/api/v1/glossaries",
            files={"file": ("large.csv", large_csv, "text/csv")},
            data={"name": "大文件测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201 or resp.status_code == 422

    async def test_unauthenticated_blocked(
        self, client: Any
    ) -> None:
        resp = await client.get("/api/v1/glossaries")
        assert resp.status_code in (401, 403)

    async def test_validation_failed_for_empty_terms(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.PRO)
        resp = await client.post(
            "/api/v1/glossaries",
            json={
                "name": "空术语",
                "terms": [{"term": "", "translation": "y", "context": None}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "validation_failed"


class TestSeedGlossaries:
    async def test_seed_loaded_on_startup(
        self, client: Any, make_user: Any
    ) -> None:
        from app.models.quota import QuotaTier

        _user, token = await make_user(tier=QuotaTier.FREE)
        resp = await client.get(
            "/api/v1/glossaries",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        system_glossaries = [g for g in data if g["is_system"]]
        assert len(system_glossaries) >= 1
        assert any(g["term_count"] >= 200 for g in system_glossaries)