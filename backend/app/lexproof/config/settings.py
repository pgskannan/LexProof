"""Configuration for LexProof cloud integrations.

Secrets are read only from the server environment. This module never exposes
credential values through health responses or frontend-facing settings.
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from .firebase_credentials import has_file_credentials


class LexProofSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=None, env_file_encoding="utf-8")

    def __init__(self, **values):
        if "_env_file" not in values and not os.getenv("LEXPROOF_USE_ENV_FILE"):
            values["_env_file"] = None
        super().__init__(**values)

    firebase_project_id: str = ""
    firebase_client_email: str = ""
    firebase_private_key: SecretStr = Field(default=SecretStr(""))
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-2.0-flash-001"
    gemini_temperature: float = 0.1
    gemini_max_output_tokens: int = 4096
    ethereum_rpc_url: str = Field(
        default="",
        validation_alias=AliasChoices("ETHEREUM_RPC_URL", "BLOCKCHAIN_RPC_URL"),
    )
    ethereum_chain_id: int = Field(default=11155111, validation_alias="ETHEREUM_CHAIN_ID")
    contract_address: str = Field(
        default="",
        validation_alias=AliasChoices("ETHEREUM_CONTRACT_ADDRESS", "CONTRACT_ADDRESS", "BLOCKCHAIN_CONTRACT_ADDRESS"),
    )
    blockchain_private_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ETHEREUM_PRIVATE_KEY", "BLOCKCHAIN_PRIVATE_KEY"),
    )
    firebase_storage_bucket: str = ""
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001,http://localhost:3002",
        validation_alias="LEXPROOF_CORS_ORIGINS",
    )
    integration_tests: bool = False
    docusign_integration_key: str = Field(default="", validation_alias="DOCUSIGN_INTEGRATION_KEY")
    docusign_user_id: str = Field(default="", validation_alias="DOCUSIGN_USER_ID")
    docusign_account_id: str = Field(default="", validation_alias="DOCUSIGN_ACCOUNT_ID")
    docusign_private_key: SecretStr = Field(default=SecretStr(""), validation_alias="DOCUSIGN_PRIVATE_KEY")
    docusign_base_url: str = Field(default="https://demo.docusign.net/restapi", validation_alias="DOCUSIGN_BASE_URL")
    docusign_auth_server: str = Field(default="account-d.docusign.com", validation_alias="DOCUSIGN_AUTH_SERVER")
    google_translate_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="GOOGLE_TRANSLATE_API_KEY")

    @property
    def project_id(self) -> str:
        return self.google_cloud_project or self.firebase_project_id

    def has_firebase_credentials(self) -> bool:
        environment_credentials = bool(
            self.firebase_project_id
            and self.firebase_client_email
            and self.firebase_private_key.get_secret_value()
        )
        return environment_credentials or has_file_credentials()

    def has_gcp_project(self) -> bool:
        return bool(self.project_id)

    def has_ai_configuration(self) -> bool:
        return bool(self.project_id and self.gemini_model)

    def has_blockchain_configuration(self) -> bool:
        return bool(self.ethereum_rpc_url and self.contract_address and self.blockchain_private_key.get_secret_value())

    def has_esignature_configuration(self) -> bool:
        """True once real DocuSign credentials are configured -- until then,
        e-signature requests are served by the stub provider so the feature
        is fully usable without any external account or credential."""
        return bool(
            self.docusign_integration_key
            and self.docusign_user_id
            and self.docusign_account_id
            and self.docusign_private_key.get_secret_value()
        )

    def has_google_translate_configuration(self) -> bool:
        """True once a real Google Cloud Translation API key is configured --
        until then, findings translation is served by the Gemini-based
        provider, which needs no separate credential since this app's
        Gemini/Vertex AI access is already configured."""
        return bool(self.google_translate_api_key.get_secret_value())

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> LexProofSettings:
    """Return the process-wide environment-backed settings instance.

    The repo includes a backend/.env file for local development. Load it when the
    app is launched from the backend directory or when the explicit override is
    enabled; otherwise the process can silently run against the wrong project
    values and Firestore credentials.
    """
    env_file = Path.cwd() / ".env"
    repo_env_file = Path(__file__).resolve().parents[3] / ".env"
    if os.getenv("LEXPROOF_USE_ENV_FILE") or env_file.exists() or repo_env_file.exists():
        load_dotenv(dotenv_path=env_file if env_file.exists() else repo_env_file)
    return LexProofSettings()
