"""Configuration for LexProof cloud integrations.

Secrets are read only from the server environment. This module never exposes
credential values through health responses or frontend-facing settings.
"""
import os
from functools import lru_cache

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
    cors_origins: str = Field(default="http://localhost:3000", validation_alias="LEXPROOF_CORS_ORIGINS")
    integration_tests: bool = False

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

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> LexProofSettings:
    """Return the process-wide environment-backed settings instance."""
    if os.getenv("LEXPROOF_USE_ENV_FILE"):
        load_dotenv()
    return LexProofSettings()
