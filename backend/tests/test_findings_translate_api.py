"""API-level tests for POST /api/findings/translate and GET /api/findings/languages."""

from fastapi.testclient import TestClient

from app.lexproof.api import findings as findings_api
from app.lexproof.main import create_app
from app.lexproof.services.auth import get_current_user
from app.lexproof.services.translation import GeminiTranslationProvider, TranslationService
from tests.fakes import FakeRepository


def reset_stores():
    FakeRepository.stores = {
        "risk_findings": {
            "f1": {
                "id": "f1",
                "owner_id": "user-1",
                "title": "Liability cap too low",
                "description": "Too low.",
                "recommendation": "Raise it.",
                "playbook_notes": "Deviates.",
            },
            "f-other-user": {"id": "f-other-user", "owner_id": "user-2", "title": "Not yours"},
        },
        "finding_translations": {},
    }


class FakeLLMProvider:
    async def complete_json(self, prompt, schema, system_prompt=None):
        import json
        import re

        match = re.search(r"Input array:\n(\[.*\])", prompt, re.DOTALL)
        texts = json.loads(match.group(1))
        return {"translations": [f"[ES] {text}" if text else "" for text in texts]}


def make_client(monkeypatch, uid: str = "user-1"):
    service = TranslationService(
        findings=FakeRepository("risk_findings"),
        translations=FakeRepository("finding_translations"),
        provider=GeminiTranslationProvider(llm=FakeLLMProvider()),
    )
    monkeypatch.setattr(findings_api, "get_translation_service", lambda: service)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"uid": uid}
    return TestClient(app)


def test_translate_findings_returns_translated_fields(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch)

    response = client.post("/api/findings/translate", json={"finding_ids": ["f1"], "target_language": "es"})

    assert response.status_code == 200
    body = response.json()
    assert body["f1"]["title"] == "[ES] Liability cap too low"
    assert body["f1"]["target_language"] == "es"


def test_translate_findings_omits_a_finding_the_caller_cannot_see(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch)

    response = client.post(
        "/api/findings/translate", json={"finding_ids": ["f1", "f-other-user"], "target_language": "es"}
    )

    assert response.status_code == 200
    assert set(response.json().keys()) == {"f1"}


def test_translate_findings_rejects_unsupported_language(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch)

    response = client.post("/api/findings/translate", json={"finding_ids": ["f1"], "target_language": "xx"})

    assert response.status_code == 400


def test_translate_findings_requires_authentication():
    reset_stores()
    response = TestClient(create_app()).post(
        "/api/findings/translate", json={"finding_ids": ["f1"], "target_language": "es"}
    )
    assert response.status_code == 401


def test_translate_findings_rejects_empty_finding_ids(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch)

    response = client.post("/api/findings/translate", json={"finding_ids": [], "target_language": "es"})
    assert response.status_code == 422


def test_list_supported_languages(monkeypatch):
    reset_stores()
    client = make_client(monkeypatch)

    response = client.get("/api/findings/languages")
    assert response.status_code == 200
    languages = response.json()["languages"]
    assert languages["es"] == "Spanish"
    assert languages["ja"] == "Japanese"
