"""Tests for the findings-translation service (services/translation.py)."""

import pytest

from app.lexproof.services.translation import (
    GeminiTranslationProvider,
    GoogleTranslateProvider,
    TranslationError,
    TranslationService,
)
from tests.fakes import FakeRepository


def reset_stores():
    FakeRepository.stores = {
        "risk_findings": {
            "f1": {
                "id": "f1",
                "owner_id": "user-1",
                "title": "Liability cap too low",
                "description": "The cap does not cover realistic exposure.",
                "recommendation": "Raise the cap to 12 months of fees.",
                "playbook_notes": "Deviates from the standard position.",
            },
            "f2": {
                "id": "f2",
                "owner_id": "user-1",
                "title": "Missing indemnity",
                "description": "",
                "recommendation": "Add mutual indemnification.",
                "playbook_notes": "",
            },
            "f-other-user": {
                "id": "f-other-user",
                "owner_id": "user-2",
                "title": "Not yours",
                "description": "x",
                "recommendation": "x",
                "playbook_notes": "x",
            },
            "f-legacy": {
                # No owner_id at all -- treated as visible, matching findings.py's _visible().
                "id": "f-legacy",
                "title": "Legacy finding",
                "description": "d",
                "recommendation": "r",
                "playbook_notes": "p",
            },
        },
        "finding_translations": {},
    }


class FakeLLMProvider:
    """A fake matching GeminiTranslationProvider's `llm` dependency shape (VertexGeminiProvider.complete_json)."""

    def __init__(self):
        self.calls: list[dict] = []

    async def complete_json(self, prompt, schema, system_prompt=None):
        import json
        import re

        self.calls.append({"prompt": prompt, "schema": schema, "system_prompt": system_prompt})
        match = re.search(r"Input array:\n(\[.*\])", prompt, re.DOTALL)
        texts = json.loads(match.group(1))
        return {"translations": [f"[ES] {text}" if text else "" for text in texts]}


def make_service(*, provider=None):
    return TranslationService(
        findings=FakeRepository("risk_findings"),
        translations=FakeRepository("finding_translations"),
        provider=provider or GeminiTranslationProvider(llm=FakeLLMProvider()),
    )


@pytest.mark.asyncio
async def test_translate_findings_translates_all_four_fields():
    reset_stores()
    service = make_service()
    results = await service.translate_findings(["f1"], "es", "user-1")
    assert results["f1"]["title"] == "[ES] Liability cap too low"
    assert results["f1"]["description"] == "[ES] The cap does not cover realistic exposure."
    assert results["f1"]["recommendation"] == "[ES] Raise the cap to 12 months of fees."
    assert results["f1"]["playbook_notes"] == "[ES] Deviates from the standard position."
    assert results["f1"]["target_language"] == "es"


@pytest.mark.asyncio
async def test_translate_findings_preserves_empty_fields_as_empty():
    reset_stores()
    service = make_service()
    results = await service.translate_findings(["f2"], "es", "user-1")
    assert results["f2"]["description"] == ""
    assert results["f2"]["playbook_notes"] == ""
    assert results["f2"]["title"] == "[ES] Missing indemnity"


@pytest.mark.asyncio
async def test_translate_findings_caches_and_does_not_re_call_provider():
    reset_stores()
    llm = FakeLLMProvider()
    service = make_service(provider=GeminiTranslationProvider(llm=llm))

    await service.translate_findings(["f1"], "es", "user-1")
    assert len(llm.calls) == 1

    results = await service.translate_findings(["f1"], "es", "user-1")
    assert len(llm.calls) == 1  # cache hit, no second call
    assert results["f1"]["title"] == "[ES] Liability cap too low"


@pytest.mark.asyncio
async def test_translate_findings_batches_multiple_findings_into_one_call():
    reset_stores()
    llm = FakeLLMProvider()
    service = make_service(provider=GeminiTranslationProvider(llm=llm))

    results = await service.translate_findings(["f1", "f2"], "es", "user-1")
    assert len(llm.calls) == 1
    assert set(results.keys()) == {"f1", "f2"}


@pytest.mark.asyncio
async def test_translate_findings_skips_a_finding_owned_by_another_user():
    reset_stores()
    service = make_service()
    results = await service.translate_findings(["f1", "f-other-user"], "es", "user-1")
    assert set(results.keys()) == {"f1"}


@pytest.mark.asyncio
async def test_translate_findings_skips_an_unknown_finding_id():
    reset_stores()
    service = make_service()
    results = await service.translate_findings(["does-not-exist"], "es", "user-1")
    assert results == {}


@pytest.mark.asyncio
async def test_translate_findings_includes_a_legacy_finding_with_no_owner():
    reset_stores()
    service = make_service()
    results = await service.translate_findings(["f-legacy"], "es", "user-1")
    assert "f-legacy" in results


@pytest.mark.asyncio
async def test_translate_findings_rejects_an_unsupported_language():
    reset_stores()
    service = make_service()
    with pytest.raises(TranslationError):
        await service.translate_findings(["f1"], "xx", "user-1")


@pytest.mark.asyncio
async def test_translate_findings_returns_empty_for_no_finding_ids():
    reset_stores()
    service = make_service()
    assert await service.translate_findings([], "es", "user-1") == {}


@pytest.mark.asyncio
async def test_google_translate_provider_calls_the_real_api_shape(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": {"translations": [{"translatedText": "[ES] Hello"}, {"translatedText": "[ES] World"}]}}

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, params=None, json=None):
            calls.append((url, params, json))
            return FakeResponse()

    import app.lexproof.services.translation as translation_module

    monkeypatch.setattr(translation_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = GoogleTranslateProvider(api_key="test-key")
    results = await provider.translate_texts(["Hello", "World"], "es")
    assert results == ["[ES] Hello", "[ES] World"]
    assert calls[0][1] == {"key": "test-key"}
    assert calls[0][2]["q"] == ["Hello", "World"]
    assert calls[0][2]["target"] == "es"


@pytest.mark.asyncio
async def test_google_translate_provider_raises_on_non_200(monkeypatch):
    class FakeResponse:
        status_code = 403
        text = "forbidden"

    class FakeAsyncClient:
        def __init__(self, timeout=None):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, params=None, json=None):
            return FakeResponse()

    import app.lexproof.services.translation as translation_module

    monkeypatch.setattr(translation_module.httpx, "AsyncClient", FakeAsyncClient)
    provider = GoogleTranslateProvider(api_key="test-key")
    with pytest.raises(TranslationError):
        await provider.translate_texts(["Hello"], "es")


def test_get_translation_provider_defaults_to_gemini_without_credentials():
    from app.lexproof.config.settings import LexProofSettings
    from app.lexproof.services.translation import get_translation_provider

    settings = LexProofSettings(google_translate_api_key="")
    provider = get_translation_provider(settings)
    assert provider.name == "gemini"


def test_get_translation_provider_selects_google_once_configured():
    from app.lexproof.config.settings import LexProofSettings
    from app.lexproof.services.translation import get_translation_provider

    settings = LexProofSettings(google_translate_api_key="a-real-key")
    provider = get_translation_provider(settings)
    assert provider.name == "google_translate"
