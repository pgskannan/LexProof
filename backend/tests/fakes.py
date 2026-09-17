"""In-memory Firestore stand-in matching FirestoreRepository's public surface."""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")


def _matches(document: dict[str, Any], field: str, op: str, value: Any) -> bool:
    current = document.get(field)
    if op == "==":
        return current == value
    if op == "array_contains":
        return value in (current or [])
    raise ValueError(f"Unsupported query operator: {op}")


class FakeRepository:
    stores: dict[str, dict[str, dict]] = {}

    def __init__(self, collection: str, settings: Any = None, client: Any = None):
        self.collection = collection
        self.settings = settings
        self._client = client

    def get(self, document_id: str, transaction: Any | None = None) -> dict[str, Any] | None:
        record = self.stores.setdefault(self.collection, {}).get(document_id)
        return dict(record) if record is not None else None

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False, transaction: Any | None = None) -> None:
        bucket = self.stores.setdefault(self.collection, {})
        if merge:
            bucket.setdefault(document_id, {}).update(data)
        else:
            bucket[document_id] = dict(data)

    def delete(self, document_id: str) -> None:
        self.stores.setdefault(self.collection, {}).pop(document_id, None)

    def stream(self) -> Iterable[dict[str, Any]]:
        return iter({"id": key, **value} for key, value in self.stores.setdefault(self.collection, {}).items())

    def query(
        self,
        *,
        equal: dict[str, Any] | None = None,
        array_contains: tuple[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        records = [{"id": key, **value} for key, value in self.stores.setdefault(self.collection, {}).items()]
        for field, value in (equal or {}).items():
            records = [item for item in records if _matches(item, field, "==", value)]
        if array_contains is not None:
            records = [item for item in records if _matches(item, array_contains[0], "array_contains", array_contains[1])]
        if order_by:
            records.sort(key=lambda item: item.get(order_by) or "", reverse=descending)
        if limit is not None:
            records = records[:limit]
        return records

    def get_many(self, document_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Batched point reads, mirroring FirestoreRepository.get_many()."""
        wanted = {str(document_id) for document_id in document_ids}
        return {
            key: {"id": key, **value}
            for key, value in self.stores.setdefault(self.collection, {}).items()
            if key in wanted
        }

    def run_transaction(self, callback: Callable[[Any], T]) -> T:
        return callback(None)
