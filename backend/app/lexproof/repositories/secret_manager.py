"""Secret Manager abstraction. Secret values are returned only to server code."""
from __future__ import annotations
from typing import Any
from ..config import LexProofSettings, get_settings


class SecretManagerRepository:
    def __init__(self, settings: LexProofSettings | None = None, client: Any = None):
        self.settings = settings or get_settings()
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import secretmanager
                self._client = secretmanager.SecretManagerServiceClient()
            except ImportError as exc:
                raise RuntimeError("google-cloud-secret-manager is required") from exc
        return self._client

    def access(self, secret_id: str, version: str = "latest") -> str:
        if not secret_id or "/" in secret_id:
            raise ValueError("secret_id must be a simple secret name")
        if not self.settings.project_id:
            raise RuntimeError("Google Cloud project is not configured")
        name = f"projects/{self.settings.project_id}/secrets/{secret_id}/versions/{version}"
        response = self._get_client().access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")
