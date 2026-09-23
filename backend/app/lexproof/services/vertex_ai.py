"""Vertex AI/Gemini provider compatible with ContractRiskEdge's LLM contract."""
from __future__ import annotations
import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any
from ..config import LexProofSettings, get_settings


class VertexAIError(Exception):
    """Raised when Vertex AI cannot complete a request."""


_RATE_LIMIT_MARKERS = ("429", "Resource exhausted", "RESOURCE_EXHAUSTED", "Too Many Requests")
_RATE_LIMIT_BACKOFF_SECONDS = (2, 6, 15)


def _is_rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


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
                    "title",
                    "severity",
                    "description",
                    "evidence",
                    "recommendation",
                    "risk_impact",
                    "compliance_impact",
                    "source_section",
                    "evidence_quote",
                    "reasoning",
                    "confidence",
                    "clause_type",
                    "playbook_alignment",
                    "playbook_notes",
                    "regulatory_citations",
                ],
            },
        },
        "key_clauses": {"type": "array", "items": {"type": "string"}},
        "compliance_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "risk_score",
        "compliance_score",
        "risk_level",
        "detected_language",
        "detected_language_name",
        "findings",
        "key_clauses",
        "compliance_items",
    ],
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

    async def _invoke_model(self, model: Any, contents: str, generation_config: Any) -> Any:
        if hasattr(model, "generate_content_async"):
            async_kwargs: dict[str, Any] = {}
            if "generation_config" in inspect.signature(model.generate_content_async).parameters:
                async_kwargs["generation_config"] = generation_config
            return await model.generate_content_async(contents, **async_kwargs)
        sync_kwargs: dict[str, Any] = {}
        if "generation_config" in inspect.signature(model.generate_content).parameters:
            sync_kwargs["generation_config"] = generation_config
        # This is a real, blocking network call to Vertex AI (it can
        # legitimately take tens of seconds - see status-and-plan.md
        # hardening item #3). It only runs when the model object has no
        # generate_content_async (an older SDK, or a sync-only test
        # double); the real Vertex SDK normally takes the awaited branch
        # above. Run it on a worker thread rather than directly on the
        # event loop -- calling it inline here would stall every other
        # request for the full duration of the Gemini call, the same
        # class of bug fixed for blockchain calls (see hardening item
        # #2 / asyncio.to_thread usage in api/blockchain.py and
        # services/ethereum_anchor_service.py).
        return await asyncio.to_thread(model.generate_content, contents, **sync_kwargs)

    async def _generate_with_retry(self, model: Any, contents: str, generation_config: Any) -> Any:
        """Retry transient Vertex quota errors instead of failing the upload.

        Live analyze returns HTTP 200 from our API only after Gemini finishes.
        A single 429 (RESOURCE_EXHAUSTED) used to surface immediately in the
        contracts UI and leave the full-lifecycle E2E waiting for a passport
        redirect that never comes. Quota errors are expected under a shared
        demo project; a short backoff is the documented recovery.
        """
        last_exc: Exception | None = None
        for delay in (*_RATE_LIMIT_BACKOFF_SECONDS, None):
            try:
                return await self._invoke_model(model, contents, generation_config)
            except VertexAIError:
                raise
            except Exception as exc:
                last_exc = exc
                if not _is_rate_limited(exc) or delay is None:
                    raise VertexAIError(f"Vertex AI request failed: {exc}") from exc
                await asyncio.sleep(delay)
        raise VertexAIError(f"Vertex AI request failed: {last_exc}") from last_exc

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
            response = await self._generate_with_retry(model, contents, generation_config)
        except VertexAIError:
            raise
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
            response = await self._generate_with_retry(model, contents, generation_config)
        except VertexAIError:
            raise
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
