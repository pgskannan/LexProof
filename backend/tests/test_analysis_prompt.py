"""The extracted prompt must be byte-identical to the inline production prompt."""

from pathlib import Path

import pytest

from app.lexproof.services.analysis_prompt import (
    ANALYSIS_PROMPT_VERSION,
    ANALYSIS_SYSTEM_PROMPT,
    build_analysis_prompt,
    build_playbook_text,
    parse_structured_analysis,
)

SERVICES = Path(__file__).resolve().parents[1] / "app" / "lexproof" / "services"


def original_production_prompt(playbook_text: str, document_text: str) -> str:
    """The exact inline prompt production analysis used before the extraction."""
    return (
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
        "Standard playbook (preferred clause positions to benchmark against):\n" + playbook_text + "\n\n"
        "Contract:\n" + document_text
    )


def test_prompt_is_byte_identical_to_the_inline_production_prompt():
    document_text = "MASTER SERVICES AGREEMENT\nSection 7. Liability."
    playbook_text = "- liability cap: cap at twelve months of fees\n- auto renewal: renewal requires written consent"

    assert build_analysis_prompt(document_text, playbook_text) == original_production_prompt(playbook_text, document_text)
    assert build_analysis_prompt(document_text) == original_production_prompt("", document_text)
    assert ANALYSIS_SYSTEM_PROMPT == "You are a legal contract risk analyst. Analyze only the supplied contract."
    assert ANALYSIS_PROMPT_VERSION == "analysis-1.0"


def test_playbook_text_uses_the_production_format():
    clauses = [
        {"clause_type": "limitation of liability", "standard_position": "cap at twelve months of fees"},
        {"clause_type": "auto renewal", "standard_position": "renewal requires written consent"},
    ]
    assert build_playbook_text(clauses) == (
        "- limitation of liability: cap at twelve months of fees\n"
        "- auto renewal: renewal requires written consent"
    )
    assert build_playbook_text(None) == ""
    assert build_playbook_text([]) == ""


def test_prompt_never_contains_answer_key_material():
    prompt = build_analysis_prompt("CONTRACT TEXT WITH Section 7", "- liability cap: standard")
    for forbidden in (
        "ground_truth_id",
        "expected_finding",
        "expected_evidence",
        "expected_severity",
        "expected_recommendation",
        "review_status",
        "evaluation_ground_truth_findings",
        "evaluation_dataset_members",
        "dataset_version_id",
        "reviewer",
    ):
        assert forbidden not in prompt


def test_production_analysis_uses_the_shared_builder_and_keeps_no_inline_copy():
    text = (SERVICES / "version_analysis.py").read_text(encoding="utf-8")
    assert "prompt = build_analysis_prompt(document_text, playbook_text)" in text
    assert "playbook_text = build_playbook_text(playbook_clauses)" in text
    assert "system_prompt = ANALYSIS_SYSTEM_PROMPT" in text
    # The instruction block lives in exactly one place now.
    assert "Return JSON only with risk_score" not in text
    assert (SERVICES / "analysis_prompt.py").read_text(encoding="utf-8").count("Return JSON only with risk_score") == 1


def test_parser_requires_findings_and_reads_fenced_json():
    assert parse_structured_analysis('{"findings": []}') == {"findings": []}
    assert parse_structured_analysis('```json\n{"findings": [{"title": "x"}]}\n```')["findings"][0]["title"] == "x"
    with pytest.raises(ValueError):
        parse_structured_analysis('{"risk_score": 10}')


def test_parser_is_still_importable_from_the_production_module():
    from app.lexproof.services.version_analysis import parse_structured_analysis as production_parser

    assert production_parser is parse_structured_analysis
