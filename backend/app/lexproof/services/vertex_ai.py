"""Vertex AI/Gemini provider compatible with ContractRiskEdge's LLM contract."""
from __future__ import annotations
import inspect
import time
from dataclasses import dataclass
from typing import Any
from ..config import LexProofSettings, get_settings


class VertexAIError(Exception):
    """Raised when Vertex AI cannot complete a request."""


ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "risk_score": {"type": "number"},
        "compliance_score": {"type": "number"},
        "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
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
                },
                "required": [
                    "title",
                    "severity",
                    "description",
                    "evidence",
                    "recommendation",
                    "risk_impact",
                    "compliance_impact",
                    "source_section",
                    "evidence_quote",
                ],
            },
        },
        "key_clauses": {"type": "array", "items": {"type": "string"}},
        "compliance_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["risk_score", "compliance_score", "risk_level", "findings", "key_clauses", "compliance_items"],
}


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


class VertexGeminiProvider:
    provider_name = "vertex_ai"

    def __init__(self, settings: LexProofSettings | None = None, model: Any = None):
        self.settings = settings or get_settings()
        self._model = model

    @property
    def supported_models(self) -> list[str]:
        return [self.settings.gemini_model]

    async def complete(self, request: Any) -> Any:
        start = time.monotonic()
        model_name = getattr(request, "model", None) or self.settings.gemini_model
        model = self._model or self._create_model(model_name)
        prompt = getattr(request, "prompt", "")
        system_prompt = getattr(request, "system_prompt", None)
        contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        try:
            from vertexai.generative_models import GenerationConfig

            generation_config = GenerationConfig(
                response_mime_type="application/json",
                response_schema=ANALYSIS_RESPONSE_SCHEMA,
                temperature=self.settings.gemini_temperature,
                max_output_tokens=self.settings.gemini_max_output_tokens,
            )
            if hasattr(model, "generate_content_async"):
                async_kwargs = {}
                if "generation_config" in inspect.signature(model.generate_content_async).parameters:
                    async_kwargs["generation_config"] = generation_config
                response = await model.generate_content_async(contents, **async_kwargs)
            else:
                sync_kwargs = {}
                if "generation_config" in inspect.signature(model.generate_content).parameters:
                    sync_kwargs["generation_config"] = generation_config
                response = model.generate_content(contents, **sync_kwargs)
        except Exception as exc:
            raise VertexAIError(f"Vertex AI request failed: {exc}") from exc
        content = getattr(response, "text", "")
        latency_ms = int((time.monotonic() - start) * 1000)
        return LLMResponse(content=content, model=model_name, provider=self.provider_name, latency_ms=latency_ms)

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Generate a JSON object using the same Vertex client as contract analysis.

        Uses a caller-supplied response schema instead of the analysis schema so
        Q&A and other structured tasks can share this provider without a second client.
        """
        import json

        model_name = self.settings.gemini_model
        model = self._model or self._create_model(model_name)
        contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        try:
            from vertexai.generative_models import GenerationConfig

            generation_config = GenerationConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=self.settings.gemini_temperature,
                max_output_tokens=self.settings.gemini_max_output_tokens,
            )
            if hasattr(model, "generate_content_async"):
                async_kwargs = {}
                if "generation_config" in inspect.signature(model.generate_content_async).parameters:
                    async_kwargs["generation_config"] = generation_config
                response = await model.generate_content_async(contents, **async_kwargs)
            else:
                sync_kwargs = {}
                if "generation_config" in inspect.signature(model.generate_content).parameters:
                    sync_kwargs["generation_config"] = generation_config
                response = model.generate_content(contents, **sync_kwargs)
        except Exception as exc:
            raise VertexAIError(f"Vertex AI request failed: {exc}") from exc
        content = getattr(response, "text", "") or ""
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]
            if stripped.endswith("```"):
                stripped = stripped[: stripped.rfind("```")]
            stripped = stripped.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise VertexAIError(f"Vertex AI returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise VertexAIError("Vertex AI returned JSON that is not an object")
        return parsed

    def _create_model(self, model_name: str) -> Any:
        if not self.settings.has_ai_configuration():
            raise VertexAIError("Google Cloud project is not configured")
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(project=self.settings.project_id, location=self.settings.google_cloud_location)
            return GenerativeModel(model_name)
        except ImportError as exc:
            raise VertexAIError("google-cloud-aiplatform is required for Vertex AI") from exc
