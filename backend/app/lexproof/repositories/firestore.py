"""Firestore repository abstraction. Collections are caller-scoped for tenant isolation."""
from __future__ import annotations
from typing import Any, Callable, Iterable, TypeVar

from ..services.firebase import initialize_firebase
from ..config import LexProofSettings

T = TypeVar("T")

# Process-wide Firestore client, created once and reused by every
# FirestoreRepository that doesn't get an explicit client injected (real
# request handlers never do -- only tests, via a fake). Constructing a new
# google.cloud.firestore.Client() is expensive (a fresh gRPC channel plus
# credential resolution on every call) and every FirestoreRepository used to
# create its own from scratch on every single request, since each request
# handler builds a fresh FirestoreRepository(...) instance. That matches the
# extreme, intermittent latency repeatedly observed in this environment
# across otherwise-unrelated endpoints (a full collection scan and a
# single-document read showing the identical symptom) -- the shared cost
# wasn't query execution, it was standing up a brand-new client/channel on
# every call, with no reuse. This caches one client for the life of the
# process, matching the Firestore client library's documented usage (the
# client is thread-safe and meant to be reused) and the same process-wide
# pattern `initialize_firebase` already uses for the Firebase Admin app.
_shared_client: Any = None

# Firestore's `in` operator accepts at most 30 values per query. Batched point
# reads are chunked at that size, which turns an N-document N+1 lookup pattern
# into ceil(N/30) round trips instead of N.
_MAX_IN_FILTER_VALUES = 30


def _get_shared_firestore_client(settings: LexProofSettings | None) -> Any:
    global _shared_client
    if _shared_client is None:
        initialize_firebase(settings)
        from google.cloud import firestore
        _shared_client = firestore.Client(project=settings.project_id if settings else None)
    return _shared_client


def reset_firestore_client_for_tests() -> None:
    """Clear the cached client. Only real integration-style tests that touch
    a real Firestore client would ever need this; unit tests use FakeRepository
    and never exercise this path at all."""
    global _shared_client
    _shared_client = None


class FirestoreRepository:
    def __init__(self, collection: str, settings: LexProofSettings | None = None, client: Any = None):
        if not collection or collection.startswith("/"):
            raise ValueError("collection must be a non-empty relative path")
        self.collection = collection
        self.settings = settings
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = _get_shared_firestore_client(self.settings)
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

    def get_many(self, document_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Batched point reads keyed by document id.

        Same result as calling `get()` for each id, but with one round trip per
        30 ids. Callers that previously looped over ids to build a lookup map
        (a classic N+1) should use this instead. Ids that do not exist are
        simply absent from the result.
        """
        ids = list(dict.fromkeys(str(document_id) for document_id in document_ids))
        if not ids:
            return {}
        from google.cloud.firestore_v1.base_query import FieldFilter
        from google.cloud.firestore_v1.field_path import FieldPath

        found: dict[str, dict[str, Any]] = {}
        for start in range(0, len(ids), _MAX_IN_FILTER_VALUES):
            chunk = ids[start:start + _MAX_IN_FILTER_VALUES]
            # The `__name__` operator takes document keys, not bare ids, so the
            # ids are resolved to references first.
            query = self._collection_ref().where(
                filter=FieldFilter(FieldPath.document_id(), "in", [self.document_ref(document_id) for document_id in chunk])
            )
            for snapshot in query.stream():
                found[snapshot.id] = {"id": snapshot.id, **(snapshot.to_dict() or {})}
        return found

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


class PassportAnchorRepository(FirestoreRepository):
    """Create-once persistence for confirmed Legal Passport ROOT anchors.

    Mirrors EvidenceAnchorRepository's create-once semantics exactly, but is
    a fully separate collection (``passport_anchors``, not
    ``evidence_anchors``) -- a passport-root anchor is never written into the
    evidence anchor collection, and vice versa, so the two anchor types can
    never collide or be confused for one another.
    """

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False) -> None:
        if self.get(document_id):
            raise ValueError(f"Passport root anchor already exists: {document_id}")
        super().set(document_id, data, merge=False)

    def delete(self, document_id: str) -> None:
        if self.get(document_id):
            raise ValueError(f"Passport root anchors cannot be deleted: {document_id}")
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
