"""Aggregates AI findings by the specific regulation(s) they cite.

Every finding may carry a `regulatory_citations` list (e.g. "GDPR Article 28",
"CCPA Section 1798.100") produced during analysis (see
`services/vertex_ai.py`'s schema and `services/version_analysis.py`'s
prompt). This module turns that per-finding list into a portfolio-wide view:
which regulations show up most across an organization's contracts, at what
severity, and where.
"""

from __future__ import annotations

from typing import Any


def build_regulation_map(
    findings: list[dict[str, Any]],
    contract_names: dict[str, str],
) -> list[dict[str, Any]]:
    by_citation: dict[str, dict[str, Any]] = {}
    for finding in findings:
        citations = finding.get("regulatory_citations") or []
        if not isinstance(citations, list):
            continue
        severity = str(finding.get("severity") or "").upper() or "UNKNOWN"
        contract_id = str(finding.get("contract_id") or "")
        contract_name = contract_names.get(contract_id, contract_id)
        for raw_citation in citations:
            citation = str(raw_citation or "").strip()
            if not citation:
                continue
            entry = by_citation.setdefault(
                citation,
                {"citation": citation, "count": 0, "severity_counts": {}, "contracts": {}},
            )
            entry["count"] += 1
            entry["severity_counts"][severity] = entry["severity_counts"].get(severity, 0) + 1
            contract_entry = entry["contracts"].setdefault(
                contract_id,
                {"contract_id": contract_id, "contract_name": contract_name, "finding_count": 0},
            )
            contract_entry["finding_count"] += 1

    result = []
    for entry in by_citation.values():
        result.append(
            {
                "citation": entry["citation"],
                "count": entry["count"],
                "severity_counts": entry["severity_counts"],
                "contracts": sorted(
                    entry["contracts"].values(), key=lambda item: item["finding_count"], reverse=True
                ),
            }
        )
    result.sort(key=lambda item: item["count"], reverse=True)
    return result
