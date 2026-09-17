"""The analysis prompt and structured-output contract for LexProof AI analysis.

This module holds the *single* implementation of the legal-analysis prompt, the
system instruction, the playbook formatting and the structured-output parser.
Production analysis (``services/version_analysis.py``) and the isolated benchmark
runner (``services/benchmark_runner.py``) both use it, so a benchmark measures
exactly the AI behaviour production ships.

It is deliberately dependency-free: it must be importable from the benchmark path
without pulling in the passport, evidence or blockchain services. It also knows
nothing about ground truth, benchmark membership or evaluation records -- the
prompt is built from the contract text and the playbook only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

ANALYSIS_PROMPT_VERSION = "analysis-1.0"

ANALYSIS_SYSTEM_PROMPT = "You are a legal contract risk analyst. Analyze only the supplied contract."

_PLAYBOOK_HEADER = "Standard playbook (preferred clause positions to benchmark against):\n"
_CONTRACT_HEADER = "\n\nContract:\n"

ANALYSIS_INSTRUCTIONS = (
    "Return JSON only with risk_score (0-100), compliance_score (0-100), risk_level, detected_language, "
    "detected_language_name, findings[], key_clauses[], and compliance_items[]. For detected_language, "
    "give the ISO 639-1 two-letter code (e.g. 'en', 'es', 'fr', 'de', 'pt', 'zh', 'ja') of the "
    "predominant language the contract text below is actually written in -- not the language of this "
    "prompt. For detected_language_name, give that language's common English name (e.g. 'English', "
    "'Spanish'). Each finding must contain: title, severity, description, "
    "evidence, recommendation, risk_impact (0-100), compliance_impact (0-100), source_section, evidence_quote, "
    "reasoning, confidence, clause_type, playbook_alignment, playbook_notes, and regulatory_citations. "
    "For source_section, cite the exact clause, section, or page reference (e.g., 'Section 7.2', 'Clause 12.3', 'Page 5'). "
    "For evidence_quote, extract the exact text from the contract that supports this finding. "
    "For reasoning, explain in 1-3 sentences WHY this specific finding was flagged -- what makes the "
    "quoted language risky or non-compliant, referencing the actual contract language, not a generic "
    "restatement of the title. For confidence, give a number from 0.0 to 1.0 reflecting how certain you "
    "are that this finding is correct and material, based only on the supplied text (lower it if the "
    "clause is ambiguous or the applicable standard is unclear; do not default to a fixed value). "
    "For clause_type, name the closest matching clause type from the playbook below, or a reasonable "
    "generic legal clause category (e.g. 'Other') if none matches. For playbook_alignment, compare the "
    "contract language against that clause type's standard position below and return exactly one of: "
    "'ALIGNED' (matches or is more favorable to the reviewing party than the standard position), "
    "'DEVIATION' (materially worse than the standard position for the reviewing party), or "
    "'NOT_COVERED' (no playbook entry addresses this clause type). For playbook_notes, give one "
    "sentence comparing the contract language to the standard position (or state plainly that no "
    "playbook entry covers it). For regulatory_citations, list specific real regulation citations "
    "(e.g. 'GDPR Article 28', 'CCPA Section 1798.100', 'HIPAA 45 CFR 164.312') that this exact finding "
    "implicates, ONLY when the flagged language plausibly engages a specific, real, well-known statute "
    "or regulation you are confident exists -- return an empty array if none clearly applies. Never "
    "invent a citation, a section number, or a regulation name; when uncertain of the exact section, "
    "cite the regulation by name only (e.g. 'GDPR') rather than guessing a section number. "
    "Do not omit fields. Use 0 when a finding truly has zero impact; "
    "never invent missing values or contract text.\n\n"
)


def build_playbook_text(clauses: Iterable[dict[str, Any]] | None) -> str:
    """Render playbook clauses exactly as the analysis prompt expects them."""
    return "\n".join(
        f"- {clause.get('clause_type')}: {clause.get('standard_position')}"
        for clause in (clauses or [])
    )


def build_analysis_prompt(document_text: str, playbook_text: str = "") -> str:
    """Build the legal-analysis prompt from contract text and playbook only.

    The instruction block, the playbook header and the contract header are the
    exact strings production has always sent, in the same order, so replacing the
    inline production prompt with this function is behaviour-preserving. The only
    variable inputs are the document text and the playbook: no ground truth, no
    benchmark membership, no reviewer notes, nothing from the evaluation side.
    """
    return (
        ANALYSIS_INSTRUCTIONS
        + _PLAYBOOK_HEADER
        + (playbook_text or "")
        + _CONTRACT_HEADER
        + (document_text or "")
    )


def parse_structured_analysis(content: str) -> dict[str, Any]:
    """Parse Gemini JSON output without manufacturing missing analysis data."""
    snippet = (content or "")[:200].strip()
    candidates = [content.strip()]
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content.strip(), re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if not isinstance(parsed.get("findings"), list):
                raise ValueError(f"Vertex AI response omitted findings (preview: {snippet})")
            return parsed

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", content):
        try:
            parsed, _ = decoder.raw_decode(content[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            if not isinstance(parsed.get("findings"), list):
                raise ValueError(f"Vertex AI response omitted findings (preview: {snippet})")
            return parsed
    raise ValueError(f"Vertex AI returned invalid structured analysis (preview: {snippet})")


# ---------------------------------------------------------------------------
# analysis-1.1 (Phase E.3 / Experiment E3-A) -- ADDITIVE ONLY.
#
# Everything above this line (ANALYSIS_PROMPT_VERSION, ANALYSIS_SYSTEM_PROMPT,
# ANALYSIS_INSTRUCTIONS, build_analysis_prompt, parse_structured_analysis) is
# untouched by this addition and remains the default prompt for every existing
# caller (production analysis and any benchmark run that does not explicitly
# opt into analysis-1.1). analysis-1.1 changes exactly one experimental
# variable: it inserts an explicit finding-coverage instruction between the
# base instructions and the playbook. Required fields, severity/evidence/
# taxonomy language, the output schema, and the playbook/contract framing are
# all unchanged from analysis-1.0. It mentions no ground truth, no benchmark
# dataset, no contract identifiers, and no target finding count.
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_VERSION_1_1 = "analysis-1.1"

_COVERAGE_INSTRUCTION = (
    "Review the entire contract text provided, section by section. Identify every "
    "material legal, commercial, and compliance risk you find -- do not stop after "
    "a fixed number of findings, and do not arbitrarily limit yourself to only the "
    "most severe or most obvious issues. If a single section contains multiple "
    "distinct risks, report each as its own finding rather than merging them into "
    "one. Do not report the same underlying issue more than once. Provide evidence "
    "for every distinct finding you report.\n\n"
)


def build_analysis_prompt_v1_1(document_text: str, playbook_text: str = "") -> str:
    """analysis-1.1: identical to build_analysis_prompt except for one inserted
    finding-coverage instruction (see _COVERAGE_INSTRUCTION above).

    Same ANALYSIS_INSTRUCTIONS, same playbook/contract headers, same required
    field list, same output schema -- the coverage instruction is the only
    difference from build_analysis_prompt, by design, so Experiment E3-A
    isolates exactly one variable.
    """
    return (
        ANALYSIS_INSTRUCTIONS
        + _COVERAGE_INSTRUCTION
        + _PLAYBOOK_HEADER
        + (playbook_text or "")
        + _CONTRACT_HEADER
        + (document_text or "")
    )
