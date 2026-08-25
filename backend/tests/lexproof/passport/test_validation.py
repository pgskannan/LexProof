"""Tests for AI Analysis Contract Validation.

This module tests the strict validation of Gemini AI analysis responses
to ensure all required fields are present and valid before creating legal passports.

Test Coverage:
- complete valid analysis
- missing risk_impact
- missing compliance_impact
- legitimate zero impact
- invalid numeric impact
- missing risk_score
- malformed findings
- valid complete passport creation
"""

import pytest
from app.lexproof.domains.passport.validation import (
    AnalysisValidationError,
    validate_analysis_response,
    validate_passport_creation_analysis,
)
from app.lexproof.services.vertex_ai import ANALYSIS_RESPONSE_SCHEMA


class TestCompleteValidAnalysis:
    """Tests for valid complete AI analysis responses."""

    def test_valid_analysis_with_all_required_fields(self):
        """Test that a complete valid analysis passes validation."""
        valid_analysis = {
            "risk_score": 75.5,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Unclear Liability Terms",
                    "severity": "high",
                    "description": "The liability clause is ambiguous and could lead to disputes.",
                    "evidence": "Clause 12.3 states liability is unlimited without clear limits.",
                    "recommendation": "Add specific liability caps and define breach conditions.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Clause 12.3 — Limitation of Liability",
                    "evidence_quote": "Each party's liability shall not exceed direct damages unless otherwise specified.",
                },
                {
                    "title": "Missing Termination Rights",
                    "severity": "medium",
                    "description": "Termination provisions are insufficient.",
                    "evidence": "Only termination for cause is mentioned, not termination for convenience.",
                    "recommendation": "Add termination for convenience with appropriate notice period.",
                    "risk_impact": 45.0,
                    "compliance_impact": 20.0,
                    "source_section": "Section 8 — Term and Termination",
                    "evidence_quote": "This Agreement may only be terminated by either party for material breach.",
                },
            ],
            "key_clauses": ["Clause 12.3", "Section 8"],
            "compliance_items": ["Liability Caps", "Termination Rights"],
        }

        # Should not raise any exception
        validate_analysis_response(valid_analysis)

    def test_analysis_schema_exports_correctly(self):
        """Test that ANALYSIS_RESPONSE_SCHEMA contains required fields."""
        # Verify the schema has expected structure
        assert "type" in ANALYSIS_RESPONSE_SCHEMA
        assert ANALYSIS_RESPONSE_SCHEMA["type"] == "object"
        assert "properties" in ANALYSIS_RESPONSE_SCHEMA
        assert "findings" in ANALYSIS_RESPONSE_SCHEMA["properties"]


class TestMissingRiskImpact:
    """Tests for missing or invalid risk_impact."""

    def test_missing_risk_impact_raises_error(self):
        """Test that missing risk_impact raises a clear error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Unclear Liability Terms",
                    "severity": "high",
                    "description": "The liability clause is ambiguous.",
                    "evidence": "Clause 12.3 states liability is unlimited.",
                    "recommendation": "Add specific liability caps.",
                    "risk_impact": None,  # Missing!
                    "compliance_impact": 30.0,
                    "source_section": "Clause 12.3",
                    "evidence_quote": "Liability is unlimited.",
                },
            ],
            "key_clauses": ["Clause 12"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "risk_impact" in str(exc_info.value.message).lower()
        assert "will silently become 0" in str(exc_info.value.message).lower()

    def test_all_findings_missing_risk_impact(self):
        """Test that all findings missing risk_impact raises error."""
        invalid_analysis = {
            "risk_score": 60.0,
            "risk_level": "medium",
            "compliance_score": 50.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": None,  # Missing
                    "compliance_impact": None,  # Missing
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
                {
                    "title": "Finding 2",
                    "severity": "medium",
                    "description": "Test finding 2.",
                    "evidence": "Evidence text 2.",
                    "recommendation": "Recommendation text 2.",
                    "risk_impact": None,  # Missing
                    "compliance_impact": None,  # Missing
                    "source_section": "Section 2",
                    "evidence_quote": "Quote text 2",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "risk_impact" in str(exc_info.value.message).lower()


class TestMissingComplianceImpact:
    """Tests for missing or invalid compliance_impact."""

    def test_missing_compliance_impact_raises_error(self):
        """Test that missing compliance_impact raises a clear error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Unclear Liability Terms",
                    "severity": "high",
                    "description": "The liability clause is ambiguous.",
                    "evidence": "Clause 12.3 states liability is unlimited.",
                    "recommendation": "Add specific liability caps.",
                    "risk_impact": 85.0,
                    "compliance_impact": None,  # Missing!
                    "source_section": "Clause 12.3",
                    "evidence_quote": "Liability is unlimited.",
                },
            ],
            "key_clauses": ["Clause 12"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "compliance_impact" in str(exc_info.value.message).lower()
        assert "will silently become 0" in str(exc_info.value.message).lower()

    def test_all_findings_missing_compliance_impact(self):
        """Test that all findings missing compliance_impact raises error."""
        invalid_analysis = {
            "risk_score": 60.0,
            "risk_level": "medium",
            "compliance_score": 50.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,  # Has risk_impact
                    "compliance_impact": None,  # Missing!
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "compliance_impact" in str(exc_info.value.message).lower()


class TestInvalidNumericImpact:
    """Tests for invalid numeric values in impact fields."""

    def test_negative_risk_impact_raises_error(self):
        """Test that negative risk_impact raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Invalid Risk",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": -10.0,  # Negative!
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "risk_impact" in str(exc_info.value.message).lower()
        assert "range [0, 100]" in str(exc_info.value.message).lower()

    def test_negative_compliance_impact_raises_error(self):
        """Test that negative compliance_impact raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Invalid Compliance",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": -5.0,  # Negative!
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "compliance_impact" in str(exc_info.value.message).lower()
        assert "range [0, 100]" in str(exc_info.value.message).lower()

    def test_non_numeric_risk_impact_raises_error(self):
        """Test that non-numeric risk_impact raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Invalid Risk",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": "high",  # String instead of number!
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "risk_impact" in str(exc_info.value.message).lower()
        assert "number" in str(exc_info.value.message).lower()


class TestMissingRiskScore:
    """Tests for missing risk_score at top level."""

    def test_missing_risk_score_raises_error(self):
        """Test that missing risk_score raises error."""
        invalid_analysis = {
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "risk_score" in str(exc_info.value.message).lower()

    def test_missing_compliance_score_raises_error(self):
        """Test that missing compliance_score raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "compliance_score" in str(exc_info.value.message).lower()


class TestMalformedFindings:
    """Tests for malformed findings structure."""

    def test_findings_is_not_a_list(self):
        """Test that findings must be a list."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": "not a list",  # String instead of list!
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "findings" in str(exc_info.value.message).lower()
        assert "list" in str(exc_info.value.message).lower()

    def test_findings_is_empty(self):
        """Test that findings list cannot be empty."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [],  # Empty list!
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "findings" in str(exc_info.value.message).lower()
        assert "empty" in str(exc_info.value.message).lower()

    def test_finding_is_not_a_dict(self):
        """Test that each finding must be a dictionary."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                "not a dict",  # String instead of dict!
                {
                    "title": "Finding 2",
                    "severity": "medium",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 45.0,
                    "compliance_impact": 20.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        # Error message contains "finding at index 0" and "must be a dictionary"
        assert "finding at index 0" in str(exc_info.value.message).lower()
        assert "must be a dictionary" in str(exc_info.value.message).lower()

    def test_missing_finding_fields(self):
        """Test that each finding must have all required fields."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    # Missing description, evidence, recommendation!
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "finding at index 0" in str(exc_info.value.message).lower()
        assert "missing required fields" in str(exc_info.value.message).lower()

    def test_empty_string_in_finding_fields(self):
        """Test that empty string fields in findings are rejected."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "",  # Empty!
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": [],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        # Error message contains "finding at index 0.title" and "cannot be empty"
        assert "finding at index 0.title" in str(exc_info.value.message).lower()
        assert "cannot be empty" in str(exc_info.value.message).lower()


class TestTopLevelFields:
    """Tests for top-level field validation."""

    def test_missing_top_level_fields(self):
        """Test that all required top-level fields are required."""
        invalid_analysis = {
            "risk_score": 75.0,
            # Missing risk_level, compliance_score, findings, key_clauses, compliance_items!
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "missing required top-level fields" in str(exc_info.value.message).lower()

    def test_analysis_result_not_a_dict(self):
        """Test that analysis result must be a dictionary."""
        invalid_analysis = "not a dict"  # String instead of dict!

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "must be a dictionary" in str(exc_info.value.message).lower()


class TestValidatePassportCreationAnalysis:
    """Tests for the convenience function used in passport creation."""

    def test_validate_passport_creation_analysis_valid(self):
        """Test that valid analysis passes through."""
        valid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Valid Finding",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 5.1",
                    "evidence_quote": "Example text from contract.",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["GDPR"],
        }

        # Should not raise any exception
        validate_passport_creation_analysis(valid_analysis)

    def test_validate_passport_creation_analysis_invalid(self):
        """Test that invalid analysis raises clear error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Valid Finding",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": None,  # Missing!
                    "compliance_impact": 30.0,
                    "source_section": "Section 1",
                    "evidence_quote": "Quote text",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_passport_creation_analysis(invalid_analysis)

        assert "risk_impact" in str(exc_info.value.message).lower()
        assert "will silently become 0" in str(exc_info.value.message).lower()


class TestSourceSectionAndEvidenceQuote:
    """Tests for source_section and evidence_quote fields (finding traceability)."""

    def test_valid_analysis_with_source_and_evidence_quote(self):
        """Test that findings with source_section and evidence_quote pass validation."""
        valid_analysis = {
            "risk_score": 85,
            "risk_level": "high",
            "compliance_score": 0,
            "findings": [
                {
                    "title": "Unilateral Fee Increase",
                    "severity": "high",
                    "description": "Supplier may modify fees without mutual agreement.",
                    "evidence": "Fee modification clause lacks bilateral consent requirement.",
                    "recommendation": "Require bilateral written agreement before any fee modification.",
                    "risk_impact": 50,
                    "compliance_impact": 25,
                    "source_section": "Section 7.2 — Pricing & Fees",
                    "evidence_quote": "Supplier may modify applicable fees upon 30 days' notice to Customer without requiring mutual written agreement.",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["General"],
        }

        # Should not raise any exception
        validate_analysis_response(valid_analysis)

    def test_missing_source_section_raises_error(self):
        """Test that missing source_section raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    # Missing source_section!
                    "evidence_quote": "Quote from contract",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "source_section" in str(exc_info.value.message).lower()

    def test_missing_evidence_quote_raises_error(self):
        """Test that missing evidence_quote raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 5.1",
                    # Missing evidence_quote!
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "evidence_quote" in str(exc_info.value.message).lower()

    def test_empty_source_section_raises_error(self):
        """Test that empty source_section raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "",  # Empty!
                    "evidence_quote": "Quote from contract",
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "source_section" in str(exc_info.value.message).lower()
        assert "cannot be empty" in str(exc_info.value.message).lower()

    def test_empty_evidence_quote_raises_error(self):
        """Test that empty evidence_quote raises error."""
        invalid_analysis = {
            "risk_score": 75.0,
            "risk_level": "medium",
            "compliance_score": 60.0,
            "findings": [
                {
                    "title": "Finding 1",
                    "severity": "high",
                    "description": "Test finding.",
                    "evidence": "Evidence text.",
                    "recommendation": "Recommendation text.",
                    "risk_impact": 85.0,
                    "compliance_impact": 30.0,
                    "source_section": "Section 5.1",
                    "evidence_quote": "",  # Empty!
                },
            ],
            "key_clauses": ["Clause 1"],
            "compliance_items": ["GDPR"],
        }

        with pytest.raises(AnalysisValidationError) as exc_info:
            validate_analysis_response(invalid_analysis)

        assert "evidence_quote" in str(exc_info.value.message).lower()
        assert "cannot be empty" in str(exc_info.value.message).lower()
