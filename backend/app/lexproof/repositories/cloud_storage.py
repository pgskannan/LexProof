"""Cloud Storage repository abstraction with no credential handling in callers."""
from __future__ import annotations
from typing import BinaryIO, Any
from ..config import LexProofSettings, get_settings


class CloudStorageRepository:
    def __init__(self, bucket_name: str | None = None, settings: LexProofSettings | None = None, bucket: Any = None):
        self.settings = settings or get_settings()
        self.bucket_name = bucket_name or self.settings.firebase_storage_bucket
        self._bucket = bucket

    def _get_bucket(self) -> Any:
        if self._bucket is None:
            if not self.bucket_name:
                raise RuntimeError("Cloud Storage bucket is not configured")
            try:
                from google.cloud import storage
                self._bucket = storage.Client(project=self.settings.project_id).bucket(self.bucket_name)
            except ImportError as exc:
                raise RuntimeError("google-cloud-storage is required") from exc
        return self._bucket

    def upload(self, name: str, data: bytes | BinaryIO, content_type: str | None = None) -> str:
        if not name or name.startswith("/") or ".." in name.split("/"):
            raise ValueError("object name must be a safe relative path")
        blob = self._get_bucket().blob(name)
        blob.upload_from_file(data, content_type=content_type) if hasattr(data, "read") else blob.upload_from_string(data, content_type=content_type)
        return f"gs://{self.bucket_name}/{name}"

    def download(self, name: str) -> bytes:
        return self._get_bucket().blob(name).download_as_bytes()

    def delete(self, name: str) -> None:
        self._get_bucket().blob(name).delete()
