"""Canonical helpers for legal evidence findings in passports."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, TypeVar

T = TypeVar("T")


def is_legal_evidence_finding(item: Dict[str, Any]) -> bool:
    """Return True for actual finding evidence records.

    Excludes the metadata record containing overall risk and compliance scores.
    """
    evidence_type = item.get("evidence_type", "")
    if hasattr(evidence_type, "value"):
        evidence_type = evidence_type.value
    if str(evidence_type) == "metadata":
        return False
    return True


def filter_legal_evidence_findings(items: Iterable[T]) -> List[T]:
    """Return only legal evidence findings, excluding score metadata records."""
    filtered: List[T] = []
    for item in items:
        if isinstance(item, dict):
            if is_legal_evidence_finding(item):
                filtered.append(item)
        else:
            evidence_type = getattr(item, "evidence_type", None)
            if hasattr(evidence_type, "value"):
                evidence_type = evidence_type.value
            if str(evidence_type) != "metadata":
                filtered.append(item)
    return filtered


def count_legal_evidence_findings(items: Iterable[Any]) -> int:
    """Count legal evidence findings using the canonical filter."""
    return len(filter_legal_evidence_findings(items))
