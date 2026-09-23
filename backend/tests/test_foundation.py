import pytest
import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.lexproof.config import LexProofSettings
from app.lexproof.repositories.cloud_storage import CloudStorageRepository
from app.lexproof.repositories.firestore import FirestoreRepository
from app.lexproof.repositories.secret_manager import SecretManagerRepository
from app.lexproof.services.firebase import reset_firebase_for_tests
from app.lexproof.services.firebase import initialize_firebase
from app.lexproof.services.firebase_auth import FirebaseAuthenticationError, verify_firebase_token
from app.lexproof.services.health import router as health_router
from app.lexproof.services.vertex_ai import VertexGeminiProvider, VertexAIError
from app.lexproof.config import firebase_credentials


async def _no_backoff(*_args, **_kwargs):
    return None


def test_firebase_credentials_from_environment():
    settings = LexProofSettings(
        firebase_project_id="project",
        firebase_client_email="client@example.com",
        firebase_private_key="key",
    )
    assert settings.has_firebase_credentials() is True


def test_firebase_credentials_from_local_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(firebase_credentials, "local_service_account_path", lambda: tmp_path / "local.json")
    (tmp_path / "local.json").write_text("test credential", encoding="utf-8")
    assert LexProofSettings().has_firebase_credentials() is True


def test_firebase_credentials_from_application_credentials(monkeypatch, tmp_path):
    credential_path = tmp_path / "configured.json"
    credential_path.write_text("test credential", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(credential_path))
    monkeypatch.setattr(firebase_credentials, "local_service_account_path", lambda: tmp_path / "missing.json")
    assert LexProofSettings().has_firebase_credentials() is True


def test_firebase_credentials_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    # Also clear the env-based credential fields explicitly, not just the
    # file-based path. Importing tests/test_tamper_demo.py (which imports
    # scripts/tamper_demo.py and scripts/restore_demo_evidence.py) loads the
    # real backend/.env at collection time via those scripts' module-level
    # load_dotenv() calls, which populates FIREBASE_CLIENT_EMAIL /
    # FIREBASE_PRIVATE_KEY / FIREBASE_PROJECT_ID with real values for the
    # rest of the pytest process (python-dotenv doesn't override already-set
    # vars, but does set ones that weren't set yet) -- this test would then
    # see real credentials and wrongly conclude they're "configured" when
    # run as part of the full suite, even though it passes in isolation.
    monkeypatch.delenv("FIREBASE_CLIENT_EMAIL", raising=False)
    monkeypatch.delenv("FIREBASE_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.setattr(firebase_credentials, "local_service_account_path", lambda: tmp_path / "missing.json")
    assert LexProofSettings().has_firebase_credentials() is False


def test_firebase_initialization_uses_local_file(monkeypatch, tmp_path):
    local_path = tmp_path / "local.json"
    local_path.write_text("test credential", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(firebase_credentials, "local_service_account_path", lambda: local_path)
    monkeypatch.setattr("app.lexproof.services.firebase.local_service_account_path", lambda: local_path)

    certificate = object()
    app = object()
    monkeypatch.setattr(credentials, "Certificate", lambda path: certificate)
    monkeypatch.setattr(firebase_admin, "initialize_app", lambda credential, options: app)
    reset_firebase_for_tests()

    assert initialize_firebase(LexProofSettings()) is app

    reset_firebase_for_tests()


def test_settings_load_dotenv_when_project_file_exists(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("FIREBASE_CLIENT_EMAIL", raising=False)
    monkeypatch.delenv("FIREBASE_PRIVATE_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "GOOGLE_CLOUD_PROJECT=dotenv-project\n"
        "FIREBASE_PROJECT_ID=dotenv-project\n"
        "FIREBASE_CLIENT_EMAIL=dotenv@example.com\n"
        "FIREBASE_PRIVATE_KEY=dotenv-key\n",
        encoding="utf-8",
    )
    from app.lexproof.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.project_id == "dotenv-project"
    assert settings.has_firebase_credentials() is True
    get_settings.cache_clear()


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


@pytest.mark.asyncio
async def test_vertex_provider_retries_rate_limit_then_succeeds(settings, monkeypatch):
    """A single 429 from Gemini used to fail analyze immediately; the
    full-lifecycle E2E then waited for a passport redirect that never came."""
    monkeypatch.setattr("app.lexproof.services.vertex_ai.asyncio.sleep", _no_backoff)
    calls = {"n": 0}

    class Response:
        text = "verified-after-retry"

    class Model:
        async def generate_content_async(self, prompt):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("429 Resource exhausted. Please try again later.")
            return Response()

    class Request:
        prompt = "check this"
        system_prompt = None
        model = None

    result = await VertexGeminiProvider(settings, model=Model()).complete(Request())
    assert result.content == "verified-after-retry"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_vertex_provider_stops_retrying_persistent_rate_limits(settings, monkeypatch):
    monkeypatch.setattr("app.lexproof.services.vertex_ai.asyncio.sleep", _no_backoff)
    calls = {"n": 0}

    class Model:
        async def generate_content_async(self, prompt):
            calls["n"] += 1
            raise RuntimeError("429 Resource exhausted. Please try again later.")

    class Request:
        prompt = "check this"
        system_prompt = None
        model = None

    with pytest.raises(VertexAIError, match="429"):
        await VertexGeminiProvider(settings, model=Model()).complete(Request())
    assert calls["n"] == 4


@pytest.mark.asyncio
async def test_vertex_provider_offloads_sync_only_model_to_a_thread(settings):
    """A model object without generate_content_async (an older SDK, or a
    sync-only double like this one) must still not block the event loop:
    complete() has to run generate_content() on a worker thread rather than
    calling it inline (hardening item #2 -- the same asyncio.to_thread
    pattern used for blockchain calls elsewhere in this codebase)."""
    import threading

    calling_thread = {}

    class Response:
        text = "verified-sync"

    class Model:
        def generate_content(self, prompt):
            calling_thread["name"] = threading.current_thread().name
            assert prompt == "check this"
            return Response()

    class Request:
        prompt = "check this"
        system_prompt = None
        model = None

    result = await VertexGeminiProvider(settings, model=Model()).complete(Request())

    assert result.content == "verified-sync"
    assert calling_thread["name"] != threading.current_thread().name


def test_vertex_provider_requires_project(monkeypatch):
    # This test needs an environment with no project configured. Delete both
    # env vars explicitly rather than relying on their ambient absence -- this
    # suite is commonly run with GOOGLE_CLOUD_PROJECT/FIREBASE_PROJECT_ID set
    # globally (other tests here need a project configured), which otherwise
    # makes LexProofSettings().project_id truthy and this guard never fires.
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    with pytest.raises(VertexAIError):
        VertexGeminiProvider(LexProofSettings())._create_model("model")


def test_health_endpoints_do_not_return_credentials(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "health-project")
    app = FastAPI()
    app.include_router(health_router)
    response = TestClient(app).get("/health/gcp")
    assert response.status_code == 200
    assert "PRIVATE_KEY" not in response.text
