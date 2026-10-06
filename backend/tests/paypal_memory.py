"""In-memory stand-in for FirestoreRepository used by PayPal unit tests."""

from __future__ import annotations

from typing import Any


class MemoryRepository:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}

    def get(self, document_id: str, transaction: Any = None) -> dict[str, Any] | None:
        data = self.docs.get(document_id)
        return dict(data) if data is not None else None

    def set(self, document_id: str, data: dict[str, Any], merge: bool = False, transaction: Any = None) -> None:
        if merge and document_id in self.docs:
            self.docs[document_id].update(data)
            return
        self.docs[document_id] = dict(data)

    def stream(self) -> list[dict[str, Any]]:
        return [{"id": key, **value} for key, value in self.docs.items()]

    def query(
        self,
        *,
        equal: dict[str, Any] | None = None,
        array_contains: tuple[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.stream()
        for field, value in (equal or {}).items():
            rows = [item for item in rows if item.get(field) == value]
        if array_contains is not None:
            key, value = array_contains
            rows = [item for item in rows if value in (item.get(key) or [])]
        if order_by:
            rows.sort(key=lambda item: item.get(order_by) or "", reverse=descending)
        if limit is not None:
            rows = rows[:limit]
        return rows

    def run_transaction(self, callback: Any) -> Any:
        return callback(None)
