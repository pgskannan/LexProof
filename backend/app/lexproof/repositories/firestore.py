"""Firestore repository abstraction. Collections are caller-scoped for tenant isolation."""
from __future__ import annotations
from typing import Any, Callable, Iterable, TypeVar

from ..services.firebase import initialize_firebase
from ..config import LexProofSettings

T = TypeVar("T")


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

    def _collection_ref(self) -> Any:
        """Resolve a top-level or nested collection path (odd number of segments)."""
        parts = [part for part in self.collection.strip("/").split("/") if part]
        if not parts or len(parts) % 2 == 0:
            raise ValueError("collection path must point to a collection (odd number of segments)")
        ref: Any = self._get_client()
        for index, part in enumerate(parts):
            ref = ref.collection(part) if index % 2 == 0 else ref.document(part)
        return ref

    def document_ref(self, document_id: str) -> Any:
        return self._collection_ref().document(document_id)

    def get(self, document_id: str, transaction: Any | None = None) -> dict[str, Any] | None:
        ref = self.document_ref(document_id)
        snapshot = ref.get(transaction=transaction) if transaction is not None else ref.get()
        return snapshot.to_dict() if snapshot.exists else None

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False, transaction: Any | None = None) -> None:
        ref = self.document_ref(document_id)
        if transaction is not None:
            transaction.set(ref, data, merge=merge)
            return
        ref.set(data, merge=merge)

    def delete(self, document_id: str) -> None:
        self.document_ref(document_id).delete()

    def stream(self) -> Iterable[dict[str, Any]]:
        for snapshot in self._collection_ref().stream():
            yield {"id": snapshot.id, **(snapshot.to_dict() or {})}

    def query(
        self,
        *,
        equal: dict[str, Any] | None = None,
        array_contains: tuple[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = self._collection_ref()
        for field, value in (equal or {}).items():
            query = query.where(field, "==", value)
        if array_contains is not None:
            query = query.where(array_contains[0], "array_contains", array_contains[1])
        if order_by:
            query = query.order_by(order_by, direction="DESCENDING" if descending else "ASCENDING")
        if limit is not None:
            query = query.limit(limit)
        return [{"id": snapshot.id, **(snapshot.to_dict() or {})} for snapshot in query.stream()]

    def run_transaction(self, callback: Callable[[Any], T]) -> T:
        """Run `callback(transaction)` atomically. Fake clients without transactions invoke it with None."""
        client = self._get_client()
        if not hasattr(client, "transaction"):
            return callback(None)
        from google.cloud import firestore

        @firestore.transactional
        def wrapped(transaction: Any) -> T:
            return callback(transaction)

        return wrapped(client.transaction())


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
