"""AI-generated, plain-English executive summary for a contract.

Turns a contract's latest AI analysis (risk/compliance scores and its
flagged findings) into a single paragraph written for a non-legal
stakeholder -- a founder, an operations lead, a board member -- who wants
the headline risk picture without reading legal findings language. Uses the
same already-configured Gemini/Vertex AI provider as every other AI feature
in this app (analysis, Ask Lexi, redline suggestions, translation), so like
translation (Task #105) this needs no stub and no new credential: it is
fully real today.

Summaries are cached per contract VERSION, not per contract, since a new
version can materially change the risk picture -- re-analyzing a contract
(which produces a new version_id) should yield a fresh summary rather than
silently keep serving one written about an earlier draft. `get_summary()`
returns the cached summary for the contract's *current* version when one
exists, and only calls the LLM on a genuine cache miss or when the caller
explicitly asks to regenerate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from ..repositories.firestore import FirestoreRepository
from .organizations import get_organization_service
from .vertex_ai import VertexAIError, VertexGeminiProvider

logger = logging.getLogger(__name__)

SUMMARIES_COLLECTION = "executive_summaries"

SEVERITY_ORDER = ["critical", "high", "medium", "low"]

SUMMARY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
    },
    "required": ["summary"],
}

SYSTEM_PROMPT = """You are LexProof's executive briefing assistant. You are given a contract's AI risk \
analysis -- scores and a list of flagged findings -- and must write ONE paragraph (roughly 80-140 words) \
in plain English for a non-legal stakeholder such as a founder, an operations lead, or a board member. Do \
not use legal jargon, clause names, or statute citations -- describe what could go wrong in practical, \
business terms (money, liability, operational disruption, compliance exposure) and end with a one-line \
bottom-line recommendation (for example "safe to sign", "needs legal review before signing", or \
"renegotiate before proceeding"). Do not use bullet points, headers, or markdown -- return prose only, one \
paragraph. Ground every claim in the findings provided; do not invent risks that are not implied by them."""


class ExecutiveSummaryError(ValueError):
    """Raised when a summary cannot be produced for a contract."""


class SummaryLLM(Protocol):
    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        ...


def _is_visible_to_user(record: dict[str, Any], uid: str) -> bool:
    """Use active organization membership for org-owned contracts."""
    org_id = record.get("org_id")
    if org_id:
        return bool(get_organization_service().get_active_member(str(org_id), uid))
    owner_id = record.get("owner_id")
    return not owner_id or owner_id == uid


class ExecutiveSummaryService:
    def __init__(
        self,
        *,
        contracts: FirestoreRepository | None = None,
        versions: FirestoreRepository | None = None,
        passports: FirestoreRepository | None = None,
        findings: FirestoreRepository | None = None,
        summaries: FirestoreRepository | None = None,
        llm: SummaryLLM | None = None,
    ) -> None:
        self.contracts = contracts or FirestoreRepository("contracts")
        self.versions = versions or FirestoreRepository("contract_versions")
        self.passports = passports or FirestoreRepository("legal_passports")
        self.findings = findings or FirestoreRepository("risk_findings")
        self.summaries = summaries or FirestoreRepository(SUMMARIES_COLLECTION)
        self.llm = llm or VertexGeminiProvider()

    async def get_summary(self, contract_id: str, actor_id: str, *, force: bool = False) -> dict[str, Any]:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise ExecutiveSummaryError(f"Contract not found: {contract_id}")
        if not _is_visible_to_user(contract, actor_id):
            raise PermissionError("You are not authorized to access this contract")

        version_id = contract.get("current_version_id")
        if not version_id:
            raise ExecutiveSummaryError("This contract has no analyzed version yet")

        if not force:
            cached = self.summaries.get(version_id)
            if cached:
                return cached

        contract_findings = [
            record
            for record in self.findings.stream()
            if record.get("contract_id") == contract_id and record.get("version_id") == version_id
        ]
        if not contract_findings:
            raise ExecutiveSummaryError(
                "This contract's current version has not been analyzed yet -- run AI analysis first"
            )

        version = self.versions.get(version_id) or {}
        passport_id = version.get("passport_id")
        passport = self.passports.get(passport_id) if passport_id else None
        risk_score = passport.get("risk_score") if passport else None
        compliance_score = passport.get("compliance_score") if passport else None
        risk_level = passport.get("risk_level") if passport else None

        severity_counts: dict[str, int] = {severity: 0 for severity in SEVERITY_ORDER}
        for record in contract_findings:
            severity = str(record.get("severity") or "").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        def _rank(record: dict[str, Any]) -> int:
            severity = str(record.get("severity") or "").lower()
            return SEVERITY_ORDER.index(severity) if severity in SEVERITY_ORDER else len(SEVERITY_ORDER)

        top_findings = sorted(contract_findings, key=_rank)[:8]

        contract_name = contract.get("name") or contract.get("contract_name") or contract_id
        prompt_lines = [
            f"Contract name: {contract_name}",
            f"Risk score: {risk_score if risk_score is not None else 'not recorded'}",
            f"Risk level: {risk_level or 'not recorded'}",
            f"Compliance score: {compliance_score if compliance_score is not None else 'not recorded'}",
            "Findings by severity: " + ", ".join(f"{count} {severity}" for severity, count in severity_counts.items()),
            "",
            "Top findings:",
        ]
        for record in top_findings:
            prompt_lines.append(
                f"- [{str(record.get('severity') or 'unknown').upper()}] "
                f"{record.get('title') or 'Untitled finding'}: {record.get('description') or 'No description recorded.'}"
            )
        prompt = "\n".join(prompt_lines)

        try:
            generated = await self.llm.complete_json(prompt, SUMMARY_RESPONSE_SCHEMA, SYSTEM_PROMPT)
        except VertexAIError:
            raise
        except Exception as exc:
            raise VertexAIError(f"Executive summary generation failed: {exc}") from exc

        summary_text = str(generated.get("summary") or "").strip()
        if not summary_text:
            raise ExecutiveSummaryError("The AI did not return a summary for this contract")

        record = {
            "contract_id": contract_id,
            "version_id": version_id,
            "summary": summary_text,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "compliance_score": compliance_score,
            "findings_by_severity": severity_counts,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.summaries.set(version_id, record)
        return record


_executive_summary_service: ExecutiveSummaryService | None = None


def get_executive_summary_service() -> ExecutiveSummaryService:
    global _executive_summary_service
    if _executive_summary_service is None:
        _executive_summary_service = ExecutiveSummaryService()
    return _executive_summary_service
