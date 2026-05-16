"""This file owns environment configuration for The Brain backend."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import lru_cache so settings are created once and reused.
from functools import lru_cache

# Import pydantic helpers so environment variables can be mapped into typed settings.
from pydantic import AliasChoices, Field, SecretStr
# Import BaseSettings so settings can be loaded from environment variables and .env.
from pydantic_settings import BaseSettings, SettingsConfigDict


# Define the settings object that represents all runtime configuration for the Brain service.
class Settings(BaseSettings):
    # Tell pydantic-settings to load values from a local .env file and ignore unrelated values.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Store the app name used in API metadata and provider headers.
    app_name: str = "Repo Explorer"
    # Store the current environment name, such as development or production.
    app_env: str = "development"
    # Store the remote LLM provider label.
    llm_provider: str = "openrouter"
    # Store the provider base URL and allow either LLM_BASE_URL or OPENROUTER_BASE_URL to set it.
    llm_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias=AliasChoices("LLM_BASE_URL", "OPENROUTER_BASE_URL"))
    # Store the model name and allow either LLM_MODEL_NAME or LLM_MODEL to set it.
    llm_model_name: str = Field(default="google/gemini-flash-1.5", validation_alias=AliasChoices("LLM_MODEL_NAME", "LLM_MODEL"))
    # Store a generic secret API key when LLM_API_KEY is used.
    llm_api_key: SecretStr | None = Field(default=None, validation_alias="LLM_API_KEY")
    # Store the OpenRouter-specific secret API key when OPENROUTER_API_KEY is used.
    openrouter_api_key: SecretStr | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    # Store the connection timeout for opening the provider HTTP connection.
    llm_connect_timeout_seconds: float = 5.0
    # Store the total request timeout for provider calls.
    llm_request_timeout_seconds: float = 30.0
    # Store how many retry attempts should happen after the first failed provider call.
    llm_max_retries: int = 2
    # Store comma-separated frontend origins that may call the API from a browser.
    backend_cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000", validation_alias=AliasChoices("BACKEND_CORS_ORIGINS", "CORS_ORIGINS"))

    # Return the first configured non-empty secret API key.
    @property
    def api_key_value(self) -> str:
        # Iterate over the supported key locations in priority order.
        for candidate in (self.llm_api_key, self.openrouter_api_key):
            # Skip missing secret values.
            if candidate is None:
                # Continue to the next possible secret value.
                continue
            # Convert the pydantic SecretStr into a stripped plain string for the Authorization header.
            value = candidate.get_secret_value().strip()
            # Return the first non-empty secret.
            if value:
                # Give the connector the usable key value.
                return value
        # Return an empty string when no key was configured.
        return ""

    # Return the CORS origins as a list for FastAPI middleware.
    @property
    def cors_origins(self) -> list[str]:
        # Allow every origin when the environment variable is explicitly set to *.
        if self.backend_cors_origins.strip() == "*":
            # Return FastAPI's wildcard origin value.
            return ["*"]
        # Split the comma-separated string into a clean list of non-empty origins.
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


# Cache settings so the app reads environment configuration once.
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Create the typed settings object from environment variables and .env.
    return Settings()
