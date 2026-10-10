"""Provider-neutral types and helpers shared by LLM integrations."""
from __future__ import annotations

import re
from dataclasses import dataclass


class LLMError(Exception):
    """Raised when an LLM provider cannot complete a request."""


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


_RATE_LIMIT_MARKERS = ("429", "Resource exhausted", "RESOURCE_EXHAUSTED", "Too Many Requests")
_RATE_LIMIT_BACKOFF_SECONDS = (2, 6, 15)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _is_rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def strip_json_fences(text: str) -> str:
    """Strip reasoning tags and Markdown fences before parsing model JSON."""
    text = _THINK_BLOCK.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text[: text.rstrip().rfind("```")]
    text = text.strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text.strip()


ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_score": {"type": "number"},
        "compliance_score": {"type": "number"},
        "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        "detected_language": {"type": "string"},
        "detected_language_name": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                    "description": {"type": "string"},
                    "evidence": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "risk_impact": {"type": "number"},
                    "compliance_impact": {"type": "number"},
                    "source_section": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "confidence": {"type": "number"},
                    "clause_type": {"type": "string"},
                    "playbook_alignment": {"type": "string", "enum": ["ALIGNED", "DEVIATION", "NOT_COVERED"]},
                    "playbook_notes": {"type": "string"},
                    "regulatory_citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "title", "severity", "description", "evidence", "recommendation", "risk_impact",
                    "compliance_impact", "source_section", "evidence_quote", "reasoning", "confidence",
                    "clause_type", "playbook_alignment", "playbook_notes", "regulatory_citations",
                ],
            },
        },
        "key_clauses": {"type": "array", "items": {"type": "string"}},
        "compliance_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "risk_score", "compliance_score", "risk_level", "detected_language", "detected_language_name",
        "findings", "key_clauses", "compliance_items",
    ],
}


def ai_provider_label(provider: str | None, model: str | None) -> str:
    provider_key = (provider or "").lower()
    model_key = (model or "").lower()
    if "nemotron-3-ultra" in model_key:
        return "NVIDIA Nemotron 3 Ultra · Nebius Token Factory"
    if "nemotron-3-super" in model_key:
        return "NVIDIA Nemotron 3 Super · Nebius Token Factory"
    if provider_key in {"nebius", "nebius_token_factory"} or "nemotron" in model_key:
        return "NVIDIA Nemotron · Nebius Token Factory"
    if provider_key in {"vertex", "vertex_ai", "gemini"} or "gemini" in model_key:
        return "Google Gemini · Vertex AI"
    return "AI provider"