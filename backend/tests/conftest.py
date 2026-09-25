import os
import pytest
from app.lexproof.config import LexProofSettings


@pytest.fixture
def settings() -> LexProofSettings:
    return LexProofSettings(
        firebase_project_id="test-project",
        firebase_client_email="test@example.com",
        firebase_private_key="test-key",
        google_cloud_project="test-project",
        gemini_model="test-model",
    )


@pytest.fixture
def integration_enabled() -> bool:
    return os.getenv("INTEGRATION_TESTS", "false").lower() == "true"


@pytest.fixture(autouse=True)
def _reset_executive_summary_cache():
    """The org executive-summary endpoint caches per org for 60s; never let a
    cached result from one test leak into another."""
    from app.lexproof.api.portfolio import reset_executive_summary_cache

    reset_executive_summary_cache()
    yield
    reset_executive_summary_cache()
