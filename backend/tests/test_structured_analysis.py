import pytest

from app.lexproof.api.contracts import parse_structured_analysis


VALID = {
    "risk_score": 75,
    "risk_level": "HIGH",
    "findings": [
        {
            "title": "Auto-renewal",
            "severity": "HIGH",
            "description": "The contract renews automatically.",
            "evidence": "Section 2",
            "recommendation": "Add a notice period.",
        }
    ],
    "key_clauses": ["Auto-renewal"],
    "compliance_items": [],
}


def test_parses_valid_json():
    import json

    assert parse_structured_analysis(json.dumps(VALID)) == VALID


def test_parses_fenced_json():
    import json

    assert parse_structured_analysis(f"```json\n{json.dumps(VALID)}\n```") == VALID


def test_parses_first_complete_json_object():
    import json

    assert parse_structured_analysis(f"Here is the result:\n{json.dumps(VALID)}\nDone") == VALID


def test_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid structured analysis"):
        parse_structured_analysis("not JSON")


def test_rejects_missing_findings():
    with pytest.raises(ValueError, match="omitted findings"):
        parse_structured_analysis('{"risk_score": 10}')


def test_accepts_valid_empty_findings_list():
    import json

    analysis = {**VALID, "findings": []}
    assert parse_structured_analysis(json.dumps(analysis)) == analysis
