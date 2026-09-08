"""Grounded Q&A over an organization's persisted contract findings."""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from .vertex_ai import VertexAIError, VertexGeminiProvider
from ..repositories.firestore import FirestoreRepository

logger = logging.getLogger(__name__)

TOP_N = 18
STOPWORDS = {
    "the", "and", "for", "our", "are", "was", "were", "this", "that", "with",
    "have", "has", "from", "which", "what", "when", "where", "does", "did",
    "contract", "contracts", "agreement", "agreements", "clause", "clauses",
}

KNOWN_TERMS = [
    "governing law",
    "indemnification",
    "indemnity",
    "limitation of liability",
    "liability",
    "termination",
    "warranty",
    "warranties",
    "confidentiality",
    "data license",
    "assignment",
    "force majeure",
    "intellectual property",
    "non-compete",
    "noncompete",
    "privacy",
    "gdpr",
    "audit",
    "insurance",
    "payment",
    "renewal",
    "notice",
    "dispute",
    "arbitration",
    "jurisdiction",
    "data protection",
    "service level",
    "exclusivity",
    "change of control",
]

SEVERITY_SCORE = {"critical": 4, "high": 3, "medium": 2, "low": 1}

ASK_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string"},
                    "evidence_id": {"type": "string"},
                },
                "required": ["finding_id"],
            },
        },
    },
    "required": ["answer", "citations"],
}

SYSTEM_PROMPT = """You are LexProof's grounded contract copilot.
Answer ONLY from the retrieved findings provided in the user message.
Every factual claim must cite a finding_id (and evidence_id when present) from that list.
If the findings do not contain enough information to answer, say so clearly instead of speculating.
Do not invent contracts, clauses, finding IDs, or evidence IDs.
Do not use general legal knowledge that is not in the retrieved findings."""

UNGROUNDED_MESSAGE = (
    "I don't have enough information in your verified findings to answer that. "
    "Try naming a contract or asking about a clause type that appears in your portfolio "
    "(for example governing law, liability, termination, or indemnification)."
)


class AskLLM(Protocol):
    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        ...


def tokenize_question(question: str) -> list[str]:
    lowered = question.lower()
    terms: list[str] = []
    for phrase in KNOWN_TERMS:
        if phrase in lowered:
            terms.append(phrase)
    for token in re.findall(r"[a-z0-9][a-z0-9\-']{2,}", lowered):
        if token not in STOPWORDS and token not in terms:
            terms.append(token)
    return terms


def score_finding(finding: dict[str, Any], terms: list[str]) -> tuple[int, int]:
    haystack = " ".join(
        str(finding.get(field) or "")
        for field in ("title", "description", "evidence", "evidence_quote", "source_section", "recommendation", "severity")
    ).lower()
    keyword_score = 0
    for term in terms:
        if term in haystack:
            keyword_score += 3 if len(term) > 8 else 2
    severity_score = SEVERITY_SCORE.get(str(finding.get("severity") or "").lower(), 0)
    return keyword_score, keyword_score + severity_score


def named_contracts(question: str, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lowered = question.lower()
    matches: list[tuple[int, dict[str, Any]]] = []
    for contract in contracts:
        name = str(contract.get("name") or "").strip()
        contract_id = str(contract.get("contract_id") or contract.get("id") or "")
        if contract_id and contract_id.lower() in lowered:
            matches.append((len(contract_id) + 50, contract))
            continue
        if name and name.lower() in lowered:
            matches.append((len(name), contract))
            continue
        significant = [
            token
            for token in re.findall(r"[a-z0-9][a-z0-9\-']{3,}", name.lower())
            if token not in STOPWORDS
        ]
        if significant and all(token in lowered for token in significant):
            matches.append((sum(len(token) for token in significant), contract))
    matches.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in matches]


def _finding_id(record: dict[str, Any]) -> str:
    return str(record.get("finding_id") or record.get("id") or "")


def _contract_id(record: dict[str, Any]) -> str:
    return str(record.get("contract_id") or record.get("id") or "")


def match_evidence_id(finding: dict[str, Any], evidence_items: list[dict[str, Any]]) -> str | None:
    finding_id = _finding_id(finding)
    title = str(finding.get("title") or "").strip().lower()
    for item in evidence_items:
        if item.get("analysis_reference") and str(item.get("analysis_reference")) == finding_id:
            return str(item.get("evidence_id") or item.get("id") or "") or None
        item_title = str(item.get("title") or "").lower()
        if title and title in item_title:
            return str(item.get("evidence_id") or item.get("id") or "") or None
    return None


def validate_citations(
    claimed: list[dict[str, Any]],
    retrieved: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_finding = {_finding_id(item): item for item in retrieved if _finding_id(item)}
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in claimed:
        finding_id = str(citation.get("finding_id") or "")
        if not finding_id or finding_id in seen or finding_id not in by_finding:
            continue
        record = by_finding[finding_id]
        expected_evidence = record.get("evidence_id")
        claimed_evidence = citation.get("evidence_id")
        evidence_id = expected_evidence
        if claimed_evidence and expected_evidence and str(claimed_evidence) != str(expected_evidence):
            evidence_id = expected_evidence
        elif claimed_evidence and not expected_evidence:
            evidence_id = None
        validated.append(
            {
                "finding_id": finding_id,
                "evidence_id": evidence_id,
                "contract_id": record.get("contract_id"),
                "contract_name": record.get("contract_name"),
            }
        )
        seen.add(finding_id)
    return validated


class AskContractsService:
    def __init__(
        self,
        *,
        contracts: FirestoreRepository | None = None,
        findings: FirestoreRepository | None = None,
        evidence: FirestoreRepository | None = None,
        llm: AskLLM | None = None,
    ):
        self.contracts = contracts or FirestoreRepository("contracts")
        self.findings = findings or FirestoreRepository("risk_findings")
        self.evidence = evidence or FirestoreRepository("evidence_records")
        self.llm = llm or VertexGeminiProvider()

    def org_contracts(self, org_id: str, actor_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for contract in self.contracts.stream():
            contract_org = contract.get("org_id")
            owner_id = contract.get("owner_id")
            if contract_org == org_id or (not contract_org and (not owner_id or owner_id == actor_id)):
                records.append(
                    {
                        **contract,
                        "contract_id": _contract_id(contract),
                        "name": contract.get("name") or contract.get("contract_name") or _contract_id(contract),
                    }
                )
        return records

    def retrieve(self, org_id: str, question: str, actor_id: str) -> list[dict[str, Any]]:
        contracts = self.org_contracts(org_id, actor_id)
        if not contracts:
            return []
        contract_ids = {item["contract_id"] for item in contracts if item.get("contract_id")}
        names = {item["contract_id"]: item.get("name") or item["contract_id"] for item in contracts}
        scoped = named_contracts(question, contracts)
        scoped_ids = {item["contract_id"] for item in scoped} if scoped else contract_ids
        evidence_by_contract: dict[str, list[dict[str, Any]]] = {}
        for item in self.evidence.stream():
            cid = str(item.get("contract_id") or "")
            if cid in scoped_ids:
                evidence_by_contract.setdefault(cid, []).append(item)
        terms = tokenize_question(question)
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for finding in self.findings.stream():
            cid = str(finding.get("contract_id") or "")
            if cid not in scoped_ids:
                continue
            decorated = {
                **finding,
                "finding_id": _finding_id(finding),
                "contract_id": cid,
                "contract_name": names.get(cid, cid),
                "evidence_id": match_evidence_id(finding, evidence_by_contract.get(cid, [])),
            }
            keyword_score, total_score = score_finding(decorated, terms)
            ranked.append((keyword_score, total_score, decorated))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if scoped:
            return [item for _keyword, _total, item in ranked[:TOP_N]]
        return [item for keyword_score, _total, item in ranked if keyword_score > 0][:TOP_N]

    async def ask(self, org_id: str, question: str, actor_id: str) -> dict[str, Any]:
        retrieved = self.retrieve(org_id, question.strip(), actor_id)
        if not retrieved:
            return {"answer": UNGROUNDED_MESSAGE, "citations": [], "grounded": False}

        context_lines = []
        for item in retrieved:
            context_lines.append(
                "\n".join(
                    [
                        f"finding_id: {item.get('finding_id')}",
                        f"evidence_id: {item.get('evidence_id') or ''}",
                        f"contract_id: {item.get('contract_id')}",
                        f"contract_name: {item.get('contract_name')}",
                        f"version_id: {item.get('version_id') or ''}",
                        f"title: {item.get('title') or ''}",
                        f"severity: {item.get('severity') or ''}",
                        f"description: {item.get('description') or ''}",
                        f"source_section: {item.get('source_section') or ''}",
                        f"evidence_quote: {item.get('evidence_quote') or item.get('evidence') or ''}",
                        f"recommendation: {item.get('recommendation') or ''}",
                    ]
                )
            )
        prompt = (
            f"Question: {question.strip()}\n\n"
            "Retrieved findings (the only allowed source of facts):\n\n"
            + "\n---\n".join(context_lines)
        )
        try:
            generated = await self.llm.complete_json(prompt, ASK_RESPONSE_SCHEMA, SYSTEM_PROMPT)
        except VertexAIError:
            raise
        except Exception as exc:
            raise VertexAIError(f"Ask generation failed: {exc}") from exc

        citations = validate_citations(list(generated.get("citations") or []), retrieved)
        answer = str(generated.get("answer") or "").strip()
        if not answer:
            return {"answer": UNGROUNDED_MESSAGE, "citations": [], "grounded": False}
        return {"answer": answer, "citations": citations, "grounded": True}


_ask_service: AskContractsService | None = None


def get_ask_service() -> AskContractsService:
    global _ask_service
    if _ask_service is None:
        _ask_service = AskContractsService()
    return _ask_service
