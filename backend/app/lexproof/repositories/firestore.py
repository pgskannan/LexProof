"""Firestore repository abstraction. Collections are caller-scoped for tenant isolation."""
from __future__ import annotations
from typing import Any, Iterable
from ..services.firebase import initialize_firebase
from ..config import LexProofSettings


class FirestoreRepository:
    def __init__(self, collection: str, settings: LexProofSettings | None = None, client: Any = None):
        if not collection or collection.startswith("/"):
            raise ValueError("collection must be a non-empty relative path")
        self.collection = collection
        self.settings = settings
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            initialize_firebase(self.settings)
            from google.cloud import firestore
            self._client = firestore.Client(project=self.settings.project_id if self.settings else None)
        return self._client

    def get(self, document_id: str) -> dict[str, Any] | None:
        snapshot = self._get_client().collection(self.collection).document(document_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
        self._get_client().collection(self.collection).document(document_id).set(data, merge=merge)

    def delete(self, document_id: str) -> None:
        self._get_client().collection(self.collection).document(document_id).delete()

    def stream(self) -> Iterable[dict[str, Any]]:
        for snapshot in self._get_client().collection(self.collection).stream():
            yield {"id": snapshot.id, **(snapshot.to_dict() or {})}


class EvidenceAnchorRepository(FirestoreRepository):
    """Create-once persistence for confirmed evidence anchors."""

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
        if self.get(document_id):
            raise ValueError(f"Evidence anchor already exists: {document_id}")
        super().set(document_id, data, merge=False)

    def delete(self, document_id: str) -> None:
        if self.get(document_id):
            raise ValueError(f"Evidence anchors cannot be deleted: {document_id}")
        super().delete(document_id)


class EvidenceRecordRepository(FirestoreRepository):
    """Persistence for evidence records locked by confirmed anchors."""

    def __init__(
        self,
        anchor_repository: FirestoreRepository,
        settings: LexProofSettings | None = None,
        client: Any = None,
    ):
        super().__init__("evidence_records", settings=settings, client=client)
        self.anchor_repository = anchor_repository

    def is_evidence_anchored(self, evidence_id: str) -> bool:
        return self.anchor_repository.get(evidence_id) is not None

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
        if self.is_evidence_anchored(document_id):
            raise ValueError(f"Anchored evidence cannot be modified: {document_id}")
        super().set(document_id, data, merge=merge)

    def delete(self, document_id: str) -> None:
        if self.is_evidence_anchored(document_id):
            raise ValueError(f"Anchored evidence cannot be deleted: {document_id}")
        super().delete(document_id)
