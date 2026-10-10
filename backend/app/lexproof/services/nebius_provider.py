"""NVIDIA Nemotron provider using Nebius Token Factory's OpenAI-compatible API."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Literal

import httpx
from jsonschema import Draft202012Validator

from ..config import LexProofSettings, get_settings
from .llm_base import ANALYSIS_RESPONSE_SCHEMA, LLMError, LLMResponse, strip_json_fences

logger = logging.getLogger(__name__)


class NebiusError(LLMError):
    """Raised when Nebius Token Factory cannot complete a request."""


class NebiusNemotronProvider:
    provider_name = "nebius_token_factory"
    _RETRY_DELAYS = (2, 6, 15)
    _RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        tier: Literal["analysis", "fast"] = "analysis",
        settings: LexProofSettings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.tier = tier
        self.settings = settings or get_settings()
        self._client = client
        self.last_provider: str | None = None
        self.last_model: str | None = None
        self.last_response: LLMResponse | None = None

    @property
    def model(self) -> str:
        return self.settings.nebius_model_analysis if self.tier == "analysis" else self.settings.nebius_model_fast

    @property
    def max_tokens(self) -> int:
        return self.settings.nebius_max_tokens_analysis if self.tier == "analysis" else self.settings.nebius_max_tokens_fast

    @property
    def supported_models(self) -> list[str]:
        return [self.model]

    async def _post(self, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        url = f"{self.settings.nebius_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.nebius_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        elapsed_ms = 0
        for attempt in range(len(self._RETRY_DELAYS) + 1):
            started = time.monotonic()
            try:
                if self._client is None:
                    async with httpx.AsyncClient(timeout=self.settings.nebius_timeout_seconds) as client:
                        response = await client.post(url, headers=headers, json=body)
                else:
                    response = await self._client.post(url, headers=headers, json=body)
            except Exception as exc:
                raise NebiusError("Nebius Token Factory request failed") from None
            elapsed_ms += int((time.monotonic() - started) * 1000)
            if response.status_code in self._RETRYABLE_STATUS and attempt < len(self._RETRY_DELAYS):
                await asyncio.sleep(self._RETRY_DELAYS[attempt])
                continue
            if response.status_code >= 400:
                logger.warning("Nebius Token Factory returned HTTP %s", response.status_code)
                raise NebiusError(f"Nebius Token Factory request failed (HTTP {response.status_code})")
            try:
                return response.json(), elapsed_ms
            except (ValueError, json.JSONDecodeError) as exc:
                raise NebiusError("Nebius Token Factory returned an invalid response") from exc
        raise NebiusError("Nebius Token Factory request failed after retries")

    def _request_body(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None,
        max_tokens: int,
        *,
        force_no_think: bool = False,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        no_think = force_no_think or not self.settings.nebius_reasoning
        system = system_prompt or "You are a precise assistant. Return only the requested JSON."
        if no_think:
            system = f"{system} /no_think"
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": self.settings.nebius_temperature,
            "max_tokens": max_tokens,
            "response_format": response_format or {
                "type": "json_schema",
                "json_schema": {"name": "lexproof_response", "schema": schema, "strict": True},
            },
        }
        if no_think:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    @staticmethod
    def _parse_and_validate(content: str, schema: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        stripped = strip_json_fences(content)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return None, f"invalid JSON: {exc.msg} at char {exc.pos}"
        errors = sorted(Draft202012Validator(schema).iter_errors(parsed), key=lambda error: list(error.path))
        if errors:
            error = errors[0]
            location = "/".join(str(part) for part in error.path) or "(root)"
            return parsed if isinstance(parsed, dict) else None, f"schema error at {location}: {error.message[:240]}"
        if not isinstance(parsed, dict):
            return None, "JSON response must be an object"
        return parsed, None

    async def _complete_response(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None,
        *,
        model: str | None = None,
    ) -> LLMResponse:
        model_id = model or self.model
        started = time.monotonic()
        max_tokens = self.max_tokens
        body = self._request_body(model_id, prompt, schema, system_prompt, max_tokens)
        payload, _ = await self._post(body)
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            max_tokens = min(max_tokens * 2, 32768)
            retry_body = self._request_body(model_id, prompt, schema, system_prompt, max_tokens, force_no_think=True)
            payload, _ = await self._post(retry_body)
            choice = (payload.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                raise NebiusError("Nebius response was truncated after the token-limit retry")

        parsed, validation_error = self._parse_and_validate(content, schema)
        if validation_error:
            if finish_reason != "stop":
                raise NebiusError(f"Nebius returned invalid structured output ({validation_error})")
            repair_prompt = f"{prompt}\n\nYour previous response failed validation: {validation_error}. Return corrected JSON only."
            repair_body = self._request_body(model_id, repair_prompt, schema, system_prompt, max_tokens, force_no_think=True)
            payload, _ = await self._post(repair_body)
            choice = (payload.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            finish_reason = choice.get("finish_reason")
            parsed, validation_error = self._parse_and_validate(content, schema)
            if validation_error:
                object_prompt = (
                    f"{repair_prompt}\n\nReturn one JSON object conforming to this JSON Schema:\n"
                    f"{json.dumps(schema, separators=(',', ':'))}"
                )
                object_format = {"type": "json_object"}
                object_body = self._request_body(
                    model_id, object_prompt, schema, system_prompt, max_tokens,
                    force_no_think=True, response_format=object_format,
                )
                payload, _ = await self._post(object_body)
                choice = (payload.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content") or ""
                parsed, validation_error = self._parse_and_validate(content, schema)
                if validation_error:
                    raise NebiusError(f"Nebius returned invalid structured output ({validation_error})")

        usage = payload.get("usage") or {}
        response = LLMResponse(
            content=json.dumps(parsed, ensure_ascii=False),
            model=model_id,
            provider=self.provider_name,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        self.last_provider = response.provider
        self.last_model = response.model
        self.last_response = response
        return response

    async def complete(self, request: Any) -> LLMResponse:
        return await self._complete_response(
            getattr(request, "prompt", ""),
            ANALYSIS_RESPONSE_SCHEMA,
            getattr(request, "system_prompt", None),
            model=getattr(request, "model", None),
        )

    async def complete_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        response = await self._complete_response(prompt, schema, system_prompt)
        return json.loads(response.content)