"""AI-suggested redline language for a flagged finding.

Given a persisted finding (and, when available, the organization's playbook
standard position for that clause type), asks the same Gemini/Vertex
provider used for contract analysis and Ask Lexi to draft a replacement
clause. The suggestion is only ever a starting point: it is returned to the
caller for a human to review, edit, and explicitly save as a redline
proposal -- nothing here writes a proposal or bypasses the existing
human-approval workflow.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..repositories.firestore import FirestoreRepository
from .organizations import DEFAULT_PLAYBOOK_CLAUSES, OrganizationError, OrganizationService, get_organization_service
from .vertex_ai import VertexAIError, VertexGeminiProvider

logger = logging.getLogger(__name__)

SUGGESTION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "suggested_text": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["suggested_text", "rationale"],
}

SYSTEM_PROMPT = """You are LexProof's redline drafting assistant.
You are given one flagged finding from an AI contract review and the exact original clause text it applies to.
Draft a replacement for ONLY that clause -- a complete, legally coherent, standalone clause that resolves the
flagged issue. If an organization playbook standard position is provided, align the replacement with it.
Do not add commentary, bracketed placeholders describing what to fill in, or markdown formatting inside
suggested_text -- it must be ready to drop directly into the contract in place of the original text.
Keep the replacement's scope and defined terms consistent with the original clause; do not invent facts about
the contract that are not implied by the finding. In rationale, briefly explain (2-4 sentences) how the
replacement addresses the flagged issue."""


class RedlineSuggestionError(ValueError):
    """Raised when a suggestion cannot be produced for a finding."""


class SuggestionLLM(Protocol):
    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        ...


def _original_text(finding: dict[str, Any]) -> str:
    quote = finding.get("evidence_quote")
    if isinstance(quote, str) and quote.strip():
        return quote
    evidence = finding.get("evidence")
    if isinstance(evidence, str):
        return evidence
    if evidence is not None:
        import json

        return json.dumps(evidence)
    return ""


class RedlineSuggestionService:
    def __init__(
        self,
        *,
        contracts: FirestoreRepository | None = None,
        findings: FirestoreRepository | None = None,
        organizations: OrganizationService | None = None,
        llm: SuggestionLLM | None = None,
    ) -> None:
        self.contracts = contracts or FirestoreRepository("contracts")
        self.findings = findings or FirestoreRepository("risk_findings")
        self.organizations = organizations or get_organization_service()
        self.llm = llm or VertexGeminiProvider()

    def _playbook_standard_position(self, org_id: str | None, clause_type: str | None) -> str | None:
        if not clause_type:
            return None
        clauses = list(DEFAULT_PLAYBOOK_CLAUSES)
        if org_id:
            try:
                clauses = self.organizations.get_playbook(org_id)
            except OrganizationError:
                clauses = list(DEFAULT_PLAYBOOK_CLAUSES)
        for clause in clauses:
            if str(clause.get("clause_type") or "").strip().lower() == clause_type.strip().lower():
                return clause.get("standard_position")
        return None

    async def suggest(self, contract_id: str, finding_id: str, actor_id: str) -> dict[str, Any]:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise RedlineSuggestionError(f"Contract not found: {contract_id}")

        org_id = contract.get("org_id")
        if not org_id:
            raise PermissionError("Contract is not assigned to an organization")
        member = self.organizations.get_active_member(org_id, actor_id)
        if not member:
            raise PermissionError("You are not authorized to access this contract")

        finding = self.findings.get(finding_id)
        if not finding:
            raise RedlineSuggestionError(f"Finding not found: {finding_id}")
        if finding.get("contract_id") != contract_id:
            raise RedlineSuggestionError("Finding does not belong to the contract")

        original_text = _original_text(finding)
        if not original_text.strip():
            raise RedlineSuggestionError("This finding has no recorded clause text to redline")

        clause_type = finding.get("clause_type")
        standard_position = self._playbook_standard_position(contract.get("org_id"), clause_type)

        prompt_lines = [
            f"Finding title: {finding.get('title') or 'Untitled finding'}",
            f"Severity: {finding.get('severity') or 'Not recorded'}",
            f"Clause type: {clause_type or 'Not classified'}",
            f"Issue description: {finding.get('description') or 'Not recorded'}",
        ]
        if finding.get("reasoning"):
            prompt_lines.append(f"Why this was flagged: {finding['reasoning']}")
        if finding.get("recommendation"):
            prompt_lines.append(f"AI recommendation: {finding['recommendation']}")
        prompt_lines.append(f'Original clause text to replace exactly:\n"""\n{original_text}\n"""')
        if standard_position:
            prompt_lines.append(f"Organization playbook standard position for this clause type: {standard_position}")
        prompt = "\n\n".join(prompt_lines)

        try:
            generated = await self.llm.complete_json(prompt, SUGGESTION_RESPONSE_SCHEMA, SYSTEM_PROMPT)
        except VertexAIError:
            raise
        except Exception as exc:
            raise VertexAIError(f"Redline suggestion generation failed: {exc}") from exc

        suggested_text = str(generated.get("suggested_text") or "").strip()
        rationale = str(generated.get("rationale") or "").strip()
        if not suggested_text:
            raise RedlineSuggestionError("The AI did not return a suggested replacement for this clause")
        return {
            "suggested_text": suggested_text,
            "rationale": rationale,
            "original_text": original_text,
            "clause_type": clause_type,
            "playbook_standard_position": standard_position,
        }


_redline_suggestion_service: RedlineSuggestionService | None = None


def get_redline_suggestion_service() -> RedlineSuggestionService:
    global _redline_suggestion_service
    if _redline_suggestion_service is None:
        _redline_suggestion_service = RedlineSuggestionService()
    return _redline_suggestion_service
