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
