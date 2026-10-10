import json

import httpx
import pytest
from pydantic import SecretStr

from app.lexproof.config.settings import LexProofSettings
from app.lexproof.services.llm_base import LLMError
from app.lexproof.services.llm_factory import FallbackProvider, get_llm_provider
from app.lexproof.services.nebius_provider import NebiusError, NebiusNemotronProvider
from app.lexproof.services.vertex_ai import VertexGeminiProvider


SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
GOOD = {"answer": "grounded result"}


def _payload(content, *, finish="stop", reasoning="discard this", usage=None):
    return {
        "choices": [{
            "message": {"content": content, "reasoning_content": reasoning},
            "finish_reason": finish,
        }],
        "usage": usage or {"prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26},
    }


def _settings(**overrides):
    values = {
        "llm_provider": "nebius",
        "nebius_api_key": SecretStr("test-nebius-secret"),
        "nebius_model_analysis": "nvidia/Nemotron-3-Ultra-550b-a55b",
        "nebius_model_fast": "nvidia/Nemotron-3-Super-120b-a12b",
        "nebius_max_tokens_analysis": 64,
        "nebius_max_tokens_fast": 8,
        "nebius_timeout_seconds": 3,
    }
    values.update(overrides)
    return LexProofSettings(**values)


@pytest.mark.asyncio
async def test_strict_schema_success_ignores_reasoning_and_reports_usage():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json=_payload(json.dumps(GOOD)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider("analysis", _settings(), client=client)
        result = await provider.complete_json("analyze", SCHEMA, "system prompt")

    assert result == GOOD
    assert requests[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "lexproof_response", "schema": SCHEMA, "strict": True},
    }
    assert provider.last_response.model == "nvidia/Nemotron-3-Ultra-550b-a55b"
    assert provider.last_response.provider == "nebius_token_factory"
    assert provider.last_response.prompt_tokens == 17
    assert provider.last_response.completion_tokens == 9
    assert provider.last_response.total_tokens == 26


@pytest.mark.asyncio
async def test_default_disables_thinking_in_both_supported_ways():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json=_payload(json.dumps(GOOD), reasoning='{"answer":"wrong"}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider(settings=_settings(), client=client)
        assert await provider.complete_json("prompt", SCHEMA) == GOOD

    assert requests[0]["messages"][0]["content"].endswith(" /no_think")
    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_length_retries_once_with_thinking_off_and_doubled_limit():
    requests = []
    responses = iter([
        _payload('{"answer":"truncated', finish="length"),
        _payload(json.dumps(GOOD)),
    ])

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=next(responses))

    settings = _settings(nebius_reasoning=True)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider("fast", settings, client=client)
        assert await provider.complete_json("prompt", SCHEMA, "system") == GOOD

    assert len(requests) == 2
    assert requests[0]["max_tokens"] == 8
    assert "chat_template_kwargs" not in requests[0]
    assert requests[1]["max_tokens"] == 16
    assert requests[1]["messages"][0]["content"].endswith(" /no_think")
    assert requests[1]["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_invalid_response_is_repaired_with_validator_error():
    requests = []
    responses = iter([_payload("{}"), _payload(json.dumps(GOOD))])

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=next(responses))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider(settings=_settings(), client=client)
        assert await provider.complete_json("prompt", SCHEMA) == GOOD

    assert len(requests) == 2
    assert "previous response failed validation" in requests[1]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_invalid_repair_uses_json_object_as_last_resort(monkeypatch):
    requests = []
    responses = iter([_payload("{}"), _payload("{}"), _payload(json.dumps(GOOD))])

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=next(responses))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider(settings=_settings(), client=client)
        assert await provider.complete_json("prompt", SCHEMA) == GOOD

    assert len(requests) == 3
    assert requests[-1]["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in requests[-1]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_429_retries_with_expected_backoff(monkeypatch):
    calls = 0
    delays = []

    async def no_wait(delay):
        delays.append(delay)

    monkeypatch.setattr("app.lexproof.services.nebius_provider.asyncio.sleep", no_wait)

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=_payload(json.dumps(GOOD)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider(settings=_settings(), client=client)
        assert await provider.complete_json("prompt", SCHEMA) == GOOD

    assert calls == 2
    assert delays == [2]


@pytest.mark.asyncio
async def test_retries_5xx_and_never_exposes_api_key(monkeypatch):
    calls = 0
    monkeypatch.setattr("app.lexproof.services.nebius_provider.asyncio.sleep", lambda _: _completed_awaitable())

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="upstream error test-nebius-secret")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NebiusNemotronProvider(settings=_settings(), client=client)
        with pytest.raises(NebiusError) as error:
            await provider.complete_json("prompt", SCHEMA)

    assert calls == 4
    assert "test-nebius-secret" not in str(error.value)


async def _completed_awaitable():
    return None


def test_factory_selects_configured_nebius_and_defaults_to_vertex():
    assert isinstance(get_llm_provider("fast", _settings()), NebiusNemotronProvider)
    assert isinstance(get_llm_provider("analysis", _settings(nebius_api_key=SecretStr(""))), VertexGeminiProvider)
    assert isinstance(get_llm_provider("analysis", LexProofSettings(llm_provider="vertex")), VertexGeminiProvider)


@pytest.mark.asyncio
async def test_fallback_records_the_provider_and_model_that_answered():
    class FailedPrimary:
        provider_name = "nebius_token_factory"
        supported_models = ["nvidia/Nemotron-3-Ultra-550b-a55b"]

        async def complete_json(self, prompt, schema, system_prompt=None):
            raise NebiusError("Nebius unavailable")

    class AnsweringFallback:
        provider_name = "vertex_ai"
        supported_models = ["gemini-test"]
        last_provider = "vertex_ai"
        last_model = "gemini-test"
        last_response = None

        async def complete_json(self, prompt, schema, system_prompt=None):
            return GOOD

    fallback = FallbackProvider(FailedPrimary(), AnsweringFallback())
    assert await fallback.complete_json("prompt", SCHEMA) == GOOD
    assert fallback.last_provider == "vertex_ai"
    assert fallback.last_model == "gemini-test"
