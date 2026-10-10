"""Factory and optional cross-provider fallback for LLM features."""
from __future__ import annotations

import logging
from typing import Any, Literal

from ..config import LexProofSettings, get_settings
from .llm_base import LLMError, LLMResponse
from .nebius_provider import NebiusNemotronProvider
from .vertex_ai import VertexGeminiProvider

logger = logging.getLogger(__name__)


class FallbackProvider:
    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider_name = getattr(primary, "provider_name", "llm")
        self.last_provider: str | None = None
        self.last_model: str | None = None
        self.last_response: LLMResponse | None = None

    @property
    def supported_models(self) -> list[str]:
        return list(dict.fromkeys([*self.primary.supported_models, *self.fallback.supported_models]))

    async def complete(self, request: Any) -> LLMResponse:
        try:
            response = await self.primary.complete(request)
        except LLMError as exc:
            logger.warning("Primary AI provider failed; falling back to Vertex AI: %s", exc)
            response = await self.fallback.complete(request)
        self._record(response)
        return response

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        try:
            result = await self.primary.complete_json(prompt, schema, system_prompt)
            responder = self.primary
        except LLMError as exc:
            logger.warning("Primary AI provider failed; falling back to Vertex AI: %s", exc)
            result = await self.fallback.complete_json(prompt, schema, system_prompt)
            responder = self.fallback
        self.last_provider = getattr(responder, "last_provider", None) or getattr(responder, "provider_name", "unknown")
        self.last_model = getattr(responder, "last_model", None) or next(iter(responder.supported_models), "")
        self.last_response = getattr(responder, "last_response", None)
        return result

    def _record(self, response: LLMResponse) -> None:
        self.last_provider = response.provider
        self.last_model = response.model
        self.last_response = response


def get_llm_provider(
    tier: Literal["analysis", "fast"] = "analysis",
    settings: LexProofSettings | None = None,
) -> Any:
    settings = settings or get_settings()
    if settings.llm_provider == "nebius" and settings.has_nebius_configuration():
        primary = NebiusNemotronProvider(tier=tier, settings=settings)
        if settings.llm_fallback_to_vertex:
            return FallbackProvider(primary, VertexGeminiProvider(settings))
        return primary
    return VertexGeminiProvider(settings)