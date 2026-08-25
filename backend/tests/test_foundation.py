import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.lexproof.config import LexProofSettings
from app.lexproof.repositories.cloud_storage import CloudStorageRepository
from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.repositories.secret_manager import SecretManagerRepository
from app.lexproof.services.firebase import reset_firebase_for_tests
from app.lexproof.services.firebase_auth import FirebaseAuthenticationError, verify_firebase_token
from app.lexproof.services.health import router as health_router
from app.lexproof.services.vertex_ai import VertexGeminiProvider, VertexAIError


def test_settings_never_expose_secret_values(settings):
    assert settings.project_id == "test-project"
    assert "test-key" not in repr(settings)


def test_firebase_auth_rejects_missing_token():
    with pytest.raises(FirebaseAuthenticationError):
        verify_firebase_token("")


def test_firestore_rejects_unsafe_collection():
    with pytest.raises(ValueError):
        FirestoreRepository("/tenant-data")


def test_storage_rejects_unsafe_object(settings):
    repository = CloudStorageRepository("bucket", settings=settings, bucket=object())
    with pytest.raises(ValueError):
        repository.upload("../secret", b"data")


def test_secret_manager_rejects_unsafe_secret(settings):
    repository = SecretManagerRepository(settings=settings, client=object())
    with pytest.raises(ValueError):
        repository.access("a/b")


@pytest.mark.asyncio
async def test_vertex_provider_uses_llm_compatible_response(settings):
    class Response:
        text = "verified"

    class Model:
        async def generate_content_async(self, prompt):
            assert prompt == "check this"
            return Response()

    class Request:
        prompt = "check this"
        system_prompt = None
        model = None

    result = await VertexGeminiProvider(settings, model=Model()).complete(Request())
    assert result.content == "verified"
    assert result.provider == "vertex_ai"


def test_vertex_provider_requires_project():
    with pytest.raises(VertexAIError):
        VertexGeminiProvider(LexProofSettings())._create_model("model")


def test_health_endpoints_do_not_return_credentials(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "health-project")
    app = FastAPI()
    app.include_router(health_router)
    response = TestClient(app).get("/health/gcp")
    assert response.status_code == 200
    assert "PRIVATE_KEY" not in response.text
