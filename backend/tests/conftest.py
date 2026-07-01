from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-please-change")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    from app.core.database import Base
    from app.models import glossary, order, quota, task, user

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    sessionmaker = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, autoflush=False
    )
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def app_with_db(test_engine, monkeypatch):
    from app.api.deps import get_db
    from app.main import app
    from app.services.glossary_seed import load_seed_glossaries

    sessionmaker = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, autoflush=False
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    seed_session = sessionmaker()
    try:
        await load_seed_glossaries(seed_session)
    finally:
        await seed_session.close()

    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def client(app_with_db) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def make_user(app_with_db, test_engine):
    from app.core.security import create_access_token
    from app.models.quota import Quota, QuotaTier
    from app.models.user import User

    sessionmaker = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, autoflush=False
    )

    created: list[tuple[User, str]] = []

    async def _make(
        *,
        tier: QuotaTier = QuotaTier.FREE,
        email: str | None = None,
        phone: str | None = None,
    ) -> tuple[User, str]:
        user_id = uuid.uuid4()
        unique = uuid.uuid4().hex[:8]
        async with sessionmaker() as session:
            user = User(
                id=user_id,
                email=email or f"u-{unique}@example.com",
                phone=phone,
                password_hash="x",
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            await session.flush()
            quota = Quota(
                user_id=user_id,
                tier=tier,
                monthly_pages=30,
                daily_pages=5,
                used_pages=0,
                used_daily_pages=0,
            )
            session.add(quota)
            await session.commit()
            await session.refresh(user)
            token = create_access_token(
                {
                    "sub": str(user_id),
                    "type": "access",
                }
            )
            created.append((user, token))
            return user, token

    yield _make


@pytest.fixture
def sample_csv() -> bytes:
    rows = ["term,translation,context"]
    for i in range(50):
        rows.append(
            f"term{i},术语{i}号,上下文{i}"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def unicode_csv() -> bytes:
    return (
        "term,translation,context\n"
        "transformer,Transformer 模型,深度学习\n"
        "fine-tuning,微调,训练\n"
        "embedding,嵌入,表示学习\n"
        "梯度下降,gradient descent,优化\n"
    ).encode("gbk")


@pytest.fixture
def minimal_pdf() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n"
        b"0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n"
        b"190\n"
        b"%%EOF\n"
    )


@pytest.fixture
def dev_code() -> str:
    return "123456"


__all__: list[Any] = []
