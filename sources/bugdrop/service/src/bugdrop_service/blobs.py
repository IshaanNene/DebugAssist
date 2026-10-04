"""Object storage for screenshots, attachments and log bundles (MinIO/S3, or local files)."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Protocol


class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes | None: ...


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self.root / key
        return path.read_bytes() if path.is_file() else None


class MinioStore:
    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False
    ) -> None:
        from minio import Minio

        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.bucket = bucket
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type=content_type)

    def get(self, key: str) -> bytes | None:
        from minio.error import S3Error

        try:
            resp = self.client.get_object(self.bucket, key)
        except S3Error:
            return None
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()


def from_env() -> BlobStore:
    endpoint = os.environ.get("BUGDROP_S3_ENDPOINT")
    if endpoint:
        return MinioStore(
            endpoint,
            os.environ.get("BUGDROP_S3_ACCESS_KEY", "debugassist"),
            os.environ.get("BUGDROP_S3_SECRET_KEY", "debugassist-dev"),
            os.environ.get("BUGDROP_S3_BUCKET", "bugdrop"),
        )
    return FileStore(Path(os.environ.get("BUGDROP_FILES_DIR", "./bugdrop-files")))
