"""AI Analysis Contract Validation Module.

This module provides strict server-side validation for Gemini AI analysis responses
to ensure all required fields are present and valid before creating legal passports.

Strict Validation Requirements:
- Every finding must contain: title, severity, description, evidence, recommendation, risk_impact, compliance_impact, source_section, evidence_quote
- Top-level response must contain: risk_score, risk_level, compliance_score, findings, key_clauses, compliance_items
- Missing risk_impact/compliance_impact/source_section/evidence_quote must NOT become 0 or empty string
- Legitimate 0 values must remain 0
- Invalid numeric values must be rejected
- risk_score and compliance_score must be in range [0, 100]
- Invalid structured analysis must return a controlled 502
- Do not create a Legal Passport from invalid analysis
- Preserve existing canonical passport hashing behavior
"""

import logging
from typing import Any, Dict, List, Optional

from .models import PassportStatus

logger = logging.getLogger(__name__)

# Required top-level fields for AI analysis response
REQUIRED_TOP_LEVEL_FIELDS = {
    "risk_score",
    "risk_level",
    "compliance_score",
    "findings",
    "key_clauses",
    "compliance_items",
}

# Required fields for each finding
REQUIRED_FINDING_FIELDS = {
    "title",
    "severity",
    "description",
    "evidence",
    "recommendation",
    "risk_impact",
    "compliance_impact",
    "source_section",
    "evidence_quote",
}


class AnalysisValidationError(Exception):
    """Raised when AI analysis response fails validation."""

    def __init__(
        self,
        message: str,
        field_path: str,
        found_value: Any,
        required_value: Any,
    ):
        self.message = message
        self.field_path = field_path
        self.found_value = found_value
        self.required_value = required_value
        super().__init__(self.message)


def validate_analysis_response(analysis_result: Dict[str, Any]) -> None:
    """Validate AI analysis response structure and completeness.

    Args:
        analysis_result: AI analysis result dictionary from Gemini

    Raises:
        AnalysisValidationError: If validation fails

    This function performs strict validation to ensure:
    1. All required top-level fields are present
    2. All required finding fields are present for each finding
    3. risk_score and compliance_score are in valid range [0, 100]
    4. risk_impact and compliance_impact are NOT silently converted to 0
    5. Findings structure is valid
    """
    if not isinstance(analysis_result, dict):
        raise AnalysisValidationError(
            message="Analysis result must be a dictionary",
            field_path="root",
            found_value=analysis_result,
            required_value="dict",
        )

    # Validate top-level required fields
    missing_fields = REQUIRED_TOP_LEVEL_FIELDS - set(analysis_result.keys())
    if missing_fields:
        raise AnalysisValidationError(
            message=f"Missing required top-level fields: {', '.join(missing_fields)}",
            field_path="root",
            found_value=list(analysis_result.keys()),
            required_value=list(REQUIRED_TOP_LEVEL_FIELDS),
        )

    # Validate risk_score is present and in valid range
    risk_score = analysis_result.get("risk_score")
    if risk_score is None:
        raise AnalysisValidationError(
            message="risk_score is required but missing",
            field_path="risk_score",
            found_value=risk_score,
            required_value="number in range [0, 100]",
        )
    
    if not isinstance(risk_score, (int, float)):
        raise AnalysisValidationError(
            message="risk_score must be a number",
            field_path="risk_score",
            found_value=type(risk_score).__name__,
            required_value="number",
        )
    
    if not (0.0 <= risk_score <= 100.0):
        raise AnalysisValidationError(
            message=f"risk_score must be in range [0, 100], got {risk_score}",
            field_path="risk_score",
            found_value=risk_score,
            required_value="number in range [0, 100]",
        )

    # Validate compliance_score is present and in valid range
    compliance_score = analysis_result.get("compliance_score")
    if compliance_score is None:
        raise AnalysisValidationError(
            message="compliance_score is required but missing",
            field_path="compliance_score",
            found_value=compliance_score,
            required_value="number in range [0, 100]",
        )
    
    if not isinstance(compliance_score, (int, float)):
        raise AnalysisValidationError(
            message="compliance_score must be a number",
            field_path="compliance_score",
            found_value=type(compliance_score).__name__,
            required_value="number",
        )
    
    if not (0.0 <= compliance_score <= 100.0):
        raise AnalysisValidationError(
            message=f"compliance_score must be in range [0, 100], got {compliance_score}",
            field_path="compliance_score",
            found_value=compliance_score,
            required_value="number in range [0, 100]",
        )

    # Validate findings is a non-empty list
    findings = analysis_result.get("findings")
    if not isinstance(findings, list):
        raise AnalysisValidationError(
            message="findings must be a list",
            field_path="findings",
            found_value=type(findings).__name__ if findings is not None else None,
            required_value="list",
        )
    
    if not findings:
        raise AnalysisValidationError(
            message="findings list cannot be empty",
            field_path="findings",
            found_value=findings,
            required_value="non-empty list",
        )

    # Validate each finding has all required fields
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise AnalysisValidationError(
                message=f"Finding at index {i} must be a dictionary",
                field_path=f"findings[{i}]",
                found_value=type(finding).__name__ if finding is not None else None,
                required_value="dict",
            )

        missing_finding_fields = REQUIRED_FINDING_FIELDS - set(finding.keys())
        if missing_finding_fields:
            raise AnalysisValidationError(
                message=f"Finding at index {i} missing required fields: {', '.join(missing_finding_fields)}",
                field_path=f"findings[{i}]",
                found_value=list(finding.keys()),
                required_value=list(REQUIRED_FINDING_FIELDS),
            )

        # Validate finding fields are not silently converted to default values
        # risk_impact must be present (cannot be None)
        risk_impact = finding.get("risk_impact")
        if risk_impact is None:
            raise AnalysisValidationError(
                message=f"Finding at index {i} has None risk_impact - this will silently become 0, which is not allowed",
                field_path=f"findings[{i}].risk_impact",
                found_value=risk_impact,
                required_value="number (0-100) or legitimate 0",
            )

        # compliance_impact must be present (cannot be None)
        compliance_impact = finding.get("compliance_impact")
        if compliance_impact is None:
            raise AnalysisValidationError(
                message=f"Finding at index {i} has None compliance_impact - this will silently become 0, which is not allowed",
                field_path=f"findings[{i}].compliance_impact",
                found_value=compliance_impact,
                required_value="number (0-100) or legitimate 0",
            )

        # Validate risk_impact is a number in valid range
        if not isinstance(risk_impact, (int, float)):
            raise AnalysisValidationError(
                message=f"Finding at index {i}.risk_impact must be a number, got {type(risk_impact).__name__}",
                field_path=f"findings[{i}].risk_impact",
                found_value=risk_impact,
                required_value="number",
            )

        if not (0.0 <= risk_impact <= 100.0):
            raise AnalysisValidationError(
                message=f"Finding at index {i}.risk_impact must be in range [0, 100], got {risk_impact}",
                field_path=f"findings[{i}].risk_impact",
                found_value=risk_impact,
                required_value="number in range [0, 100]",
            )

        # Validate compliance_impact is a number in valid range
        if not isinstance(compliance_impact, (int, float)):
            raise AnalysisValidationError(
                message=f"Finding at index {i}.compliance_impact must be a number, got {type(compliance_impact).__name__}",
                field_path=f"findings[{i}].compliance_impact",
                found_value=compliance_impact,
                required_value="number",
            )

        if not (0.0 <= compliance_impact <= 100.0):
            raise AnalysisValidationError(
                message=f"Finding at index {i}.compliance_impact must be in range [0, 100], got {compliance_impact}",
                field_path=f"findings[{i}].compliance_impact",
                found_value=compliance_impact,
                required_value="number in range [0, 100]",
            )

        # Validate required string fields are non-empty
        for field_name in ["title", "severity", "description", "evidence", "recommendation", "source_section", "evidence_quote"]:
            field_value = finding.get(field_name)
            if not isinstance(field_value, str):
                raise AnalysisValidationError(
                    message=f"Finding at index {i}.{field_name} must be a non-empty string, got {type(field_value).__name__}",
                    field_path=f"findings[{i}].{field_name}",
                    found_value=field_value,
                    required_value="non-empty string",
                )
            
            if not field_value.strip():
                raise AnalysisValidationError(
                    message=f"Finding at index {i}.{field_name} cannot be empty",
                    field_path=f"findings[{i}].{field_name}",
                    found_value=field_value,
                    required_value="non-empty string",
                )

    # Validate other top-level fields are present (may be empty)
    for field in ["key_clauses", "compliance_items"]:
        if field not in analysis_result:
            logger.warning(f"Optional top-level field '{field}' missing from analysis response")

    logger.info("AI analysis response validation passed")


def validate_passport_creation_analysis(analysis_result: Dict[str, Any]) -> None:
    """Convenience function for passport creation validation.

    This function is called before creating a passport to ensure the analysis
    is valid and complete. It provides clear error messages about what went wrong.

    Args:
        analysis_result: AI analysis result dictionary from Gemini

    Raises:
        AnalysisValidationError: If validation fails

    This is the primary validation function used in PassportService.create_passport()
    """
    try:
        validate_analysis_response(analysis_result)
        logger.info("AI analysis validation passed - proceeding with passport creation")
    except AnalysisValidationError as e:
        logger.error(
            f"AI analysis validation failed: {e.message}\n"
            f"Field path: {e.field_path}\n"
            f"Found: {e.found_value}\n"
            f"Required: {e.required_value}"
        )
        raise
