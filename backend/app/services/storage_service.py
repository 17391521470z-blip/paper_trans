from __future__ import annotations

import asyncio
import io
import os
import secrets
import shutil
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings


settings = get_settings()


@dataclass(slots=True)
class StorageResult:
    key: str
    url: str | None
    size: int
    content_type: str = "application/octet-stream"


class StorageBackend(ABC):
    @abstractmethod
    async def put_object(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageResult: ...

    @abstractmethod
    async def get_object(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def delete(self, key: str) -> bool: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def generate_signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        method: str = "GET",
    ) -> str | None: ...

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageResult:
        return await self.put_object(key, data, content_type=content_type)

    async def signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        method: str = "GET",
    ) -> str | None:
        return await self.generate_signed_url(key, expires_in=expires_in, method=method)


class OSSStorage(StorageBackend):
    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str,
        region: str,
        signed_url_expire: int,
    ) -> None:
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        self.region = region
        self.signed_url_expire = signed_url_expire
        self._bucket = None

    def _ensure_bucket(self):
        if self._bucket is None:
            try:
                import oss2
            except ImportError as exc:
                raise RuntimeError("oss2 package is required for OSSStorage") from exc
            if not self.access_key_id or not self.access_key_secret:
                raise RuntimeError("OSS credentials missing")
            if not self.endpoint or not self.bucket_name:
                raise RuntimeError("OSS endpoint or bucket missing")
            auth = oss2.Auth(self.access_key_id, self.access_key_secret)
            self._bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
        return self._bucket

    async def put_object(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageResult:
        bucket = self._ensure_bucket()
        headers = {"Content-Type": content_type}
        if isinstance(data, (bytes, bytearray)):
            blob = bytes(data)
            await asyncio.to_thread(
                bucket.put_object,
                key,
                io.BytesIO(blob),
                headers,
            )
            size = len(blob)
        else:
            data.seek(0)
            content = data.read()
            size = len(content)
            await asyncio.to_thread(
                bucket.put_object,
                key,
                io.BytesIO(content),
                headers,
            )
        url = await self.generate_signed_url(key)
        return StorageResult(key=key, url=url, size=size, content_type=content_type)

    async def get_object(self, key: str) -> bytes | None:
        bucket = self._ensure_bucket()
        try:
            result = await asyncio.to_thread(bucket.get_object, key)
            data = await asyncio.to_thread(result.read)
            return data
        except Exception:
            return None

    async def delete(self, key: str) -> bool:
        bucket = self._ensure_bucket()
        try:
            await asyncio.to_thread(bucket.delete_object, key)
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        bucket = self._ensure_bucket()
        try:
            await asyncio.to_thread(bucket.head_object, key)
            return True
        except Exception:
            return False

    async def generate_signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        method: str = "GET",
    ) -> str | None:
        bucket = self._ensure_bucket()
        expire = int(expires_in or self.signed_url_expire)
        try:
            url = await asyncio.to_thread(bucket.sign_url, method, key, expire)
            return url
        except Exception:
            return None


class LocalStorage(StorageBackend):
    def __init__(
        self,
        *,
        upload_root: str | Path,
        download_root: str | Path,
        public_base_url: str = "",
        signed_token_secret: str = "",
        signed_url_expire: int = 86400,
    ) -> None:
        self.upload_root = Path(upload_root)
        self.download_root = Path(download_root)
        try:
            self.upload_root.mkdir(parents=True, exist_ok=True)
            self.download_root.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            import tempfile

            fallback = Path(tempfile.gettempdir()) / "paper-translate"
            self.upload_root = fallback / "uploads"
            self.download_root = fallback / "downloads"
            self.upload_root.mkdir(parents=True, exist_ok=True)
            self.download_root.mkdir(parents=True, exist_ok=True)
        self.public_base_url = public_base_url.rstrip("/")
        self.signed_token_secret = signed_token_secret or settings.jwt_secret
        self.signed_url_expire = signed_url_expire

    def _resolve_path(self, key: str) -> Path:
        safe_key = key.lstrip("/")
        if safe_key.startswith("uploads/"):
            rel = safe_key[len("uploads/"):]
            return self.upload_root / rel
        if safe_key.startswith("downloads/"):
            rel = safe_key[len("downloads/"):]
            return self.download_root / rel
        return self.upload_root / safe_key

    def _make_signed_token(self, key: str, expires_at: int) -> str:
        payload = f"{key}:{expires_at}"
        try:
            from app.core.security import create_access_token

            token = create_access_token(
                {
                    "sub": "storage-signed",
                    "type": "storage",
                    "key": key,
                    "exp": expires_at,
                },
                expires_delta=None,
            )
            return f"{expires_at}.{token}"
        except Exception:
            sig = secrets.token_urlsafe(8)
            return f"{expires_at}.{sig}"

    def verify_signed_token(self, key: str, token: str) -> bool:
        if not token or "." not in token:
            return False
        try:
            exp_str, _ = token.split(".", 1)
            expires_at = int(exp_str)
        except ValueError:
            return False
        if expires_at < int(time.time()):
            return False
        return True

    async def put_object(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str = "application/octet-stream",
    ) -> StorageResult:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (bytes, bytearray)):
            blob = bytes(data)
            size = len(blob)
            await asyncio.to_thread(path.write_bytes, blob)
        else:
            data.seek(0)
            blob = data.read()
            size = len(blob)
            await asyncio.to_thread(path.write_bytes, blob)
        url = await self.generate_signed_url(key)
        return StorageResult(key=key, url=url, size=size, content_type=content_type)

    async def get_object(self, key: str) -> bytes | None:
        path = self._resolve_path(key)
        if not path.is_file():
            return None
        try:
            return await asyncio.to_thread(path.read_bytes)
        except Exception:
            return None

    async def delete(self, key: str) -> bool:
        path = self._resolve_path(key)
        if not path.exists():
            return False
        try:
            if path.is_dir():
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await asyncio.to_thread(path.unlink)
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        path = self._resolve_path(key)
        return path.exists()

    async def generate_signed_url(
        self,
        key: str,
        *,
        expires_in: int | None = None,
        method: str = "GET",
    ) -> str | None:
        _ = method
        expire = int(expires_in or self.signed_url_expire)
        expires_at = int(time.time()) + expire
        token = self._make_signed_token(key, expires_at)
        base = self.public_base_url or "/api/v1/storage/local"
        return f"{base}/{key}?token={token}&exp={expires_at}"


def _is_oss_configured() -> bool:
    return bool(
        settings.oss_access_key_id
        and settings.oss_access_key_secret
        and settings.oss_endpoint
        and settings.oss_bucket
    )


def build_storage_backend() -> StorageBackend:
    if _is_oss_configured():
        return OSSStorage(
            access_key_id=settings.oss_access_key_id,
            access_key_secret=settings.oss_access_key_secret,
            endpoint=settings.oss_endpoint,
            bucket_name=settings.oss_bucket,
            region=settings.oss_region,
            signed_url_expire=settings.oss_signed_url_expire,
        )
    upload_root = Path(settings.upload_tmp_dir) / "uploads"
    download_root = Path(settings.upload_tmp_dir) / "downloads"
    return LocalStorage(
        upload_root=upload_root,
        download_root=download_root,
        public_base_url="/api/v1/storage/local",
        signed_url_expire=settings.oss_signed_url_expire,
    )


_storage_singleton: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = build_storage_backend()
    return _storage_singleton


def reset_storage_for_tests() -> None:
    global _storage_singleton
    _storage_singleton = None


def make_user_prefix(user_id: uuid.UUID, prefix: str = "uploads") -> str:
    return f"{prefix}/{user_id}"


def build_object_key(
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    filename: str,
    *,
    prefix: str = "uploads",
) -> str:
    safe_name = Path(filename).name.replace(" ", "_")
    return f"{prefix}/{user_id}/{task_id}/{safe_name}"


def build_download_prefix(user_id: uuid.UUID, task_id: uuid.UUID) -> str:
    return f"downloads/{user_id}/{task_id}"


LocalStorageBackend = LocalStorage
OSSStorageBackend = OSSStorage