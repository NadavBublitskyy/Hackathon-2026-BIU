"""This file loads Brain settings, creates the remote LLM client, and exposes setup helpers."""

# Import asyncio so retry waits can sleep without blocking FastAPI's event loop.
import asyncio
# Import logging so startup and provider errors are written to the app logs.
import logging
# Import dataclass so simple result/status containers can be declared with less boilerplate.
from dataclasses import dataclass
# Import lru_cache so settings are created once and reused.
from functools import lru_cache
# Import Lock so singleton client creation is thread-safe.
from threading import Lock
# Import Any so prompt values and raw provider responses can be typed flexibly.
from typing import Any

# Import httpx so the service can call the OpenRouter/OpenAI-compatible HTTP API.
import httpx
# Import pydantic helpers so environment variables can be mapped into typed settings.
from pydantic import AliasChoices, Field, SecretStr
# Import BaseSettings so settings can be loaded from environment variables and .env.
from pydantic_settings import BaseSettings, SettingsConfigDict

# Create a module logger so this file can report LLM setup results.
logger = logging.getLogger(__name__)


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
    llm_model_name: str = Field(default="openrouter/auto", validation_alias=AliasChoices("LLM_MODEL_NAME", "LLM_MODEL"))
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
    # Define the property used by the LLM connector to get the actual API key string.
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
    # Define the property used by main.py to configure browser access.
    def cors_origins(self) -> list[str]:
        # Allow every origin when the environment variable is explicitly set to *.
        if self.backend_cors_origins.strip() == "*":
            # Return FastAPI's wildcard origin value.
            return ["*"]
        # Split the comma-separated string into a clean list of non-empty origins.
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


# Define a small result container for successful LLM responses.
@dataclass
# Store both the extracted assistant message and the raw provider JSON.
class LLMResult:
    # Store the assistant text extracted from the provider response.
    message: str
    # Store the full provider response for debugging or advanced frontend use.
    raw: dict[str, Any]


# Define a small status container for startup readiness.
@dataclass
# Store whether the LLM client is ready and why it is not ready if setup failed.
class LLMStatus:
    # Store whether the startup ping succeeded.
    ready: bool = False
    # Store a user-facing setup error when setup failed.
    error: str | None = None
    # Store the configured provider name.
    provider: str | None = None
    # Store the configured model name.
    model: str | None = None


# Define the base exception type for LLM-related failures.
class LLMError(Exception):
    # Keep the base error class intentionally empty because its type is what matters.
    pass


# Define the exception type for missing or invalid local configuration.
class LLMConfigError(LLMError):
    # Keep this class empty so callers can catch configuration failures specifically.
    pass


# Define the exception type for provider authentication failures.
class LLMAuthError(LLMError):
    # Keep this class empty so callers can translate auth failures into HTTP 401.
    pass


# Define the class that owns all communication with the remote LLM provider.
class LLMConnector:
    # Initialize the connector with typed settings and an async HTTP client.
    def __init__(self, settings: Settings):
        # Save settings so all later requests use the same provider configuration.
        self.settings = settings
        # Track whether the startup ping has already succeeded.
        self._initialized = False
        # Create the reusable async HTTP client for all LLM requests.
        self._client = httpx.AsyncClient(base_url=settings.llm_base_url.rstrip("/"), timeout=httpx.Timeout(timeout=settings.llm_request_timeout_seconds, connect=settings.llm_connect_timeout_seconds), headers=self._headers())

    # Build the HTTP headers required by the remote LLM API.
    def _headers(self) -> dict[str, str]:
        # Read the usable API key from settings.
        api_key = self.settings.api_key_value
        # Fail clearly when no key was configured.
        if not api_key:
            # Raise a configuration error that main.py can return to the frontend.
            raise LLMConfigError("LLM_API_KEY or OPENROUTER_API_KEY is not configured.")
        # Return the provider headers used on every request.
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-Title": self.settings.app_name}

    # Ping the provider once so startup can confirm the key and network are working.
    async def initialize(self) -> None:
        # Avoid a second ping when the connector is already initialized.
        if self._initialized:
            # End early because initialization already happened.
            return
        # Send a tiny request to validate provider connectivity.
        await self.send_messages(messages=[{"role": "user", "content": "ping"}], temperature=0, max_tokens=1)
        # Mark the connector as initialized after a successful ping.
        self._initialized = True
        # Log the required startup success message.
        logger.info("LLM Client Initialized")

    # Close the async HTTP client during FastAPI shutdown.
    async def close(self) -> None:
        # Release the underlying network resources.
        await self._client.aclose()

    # Send an already-built list of chat messages to the remote LLM.
    async def send_messages(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 800) -> LLMResult:
        # Build the OpenAI-compatible chat completion request body.
        payload = {"model": self.settings.llm_model_name, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        # Send the request and retry transient provider failures.
        raw = await self._request_with_retries("POST", "/chat/completions", json=payload)
        # Return both the extracted text and the raw provider response.
        return LLMResult(message=self._extract_text(raw), raw=raw)

    # Fill a human prompt template, wrap it with a system prompt, and send both to the LLM.
    async def send_message_to_llm_wrapped_by(self, system_prompt: str, human_prompt_template: str, values: dict[str, Any] | None = None, temperature: float = 0.2, max_tokens: int = 1200) -> LLMResult:
        # Convert prompt values into a safe dict that leaves missing placeholders visible.
        prompt_values = SafePromptValues(values or {})
        # Format the human prompt with the provided values.
        human_prompt = human_prompt_template.format_map(prompt_values)
        # Send the wrapped system and human messages to the provider.
        return await self.send_messages(messages=[{"role": "system", "content": system_prompt.strip()}, {"role": "user", "content": human_prompt.strip()}], temperature=temperature, max_tokens=max_tokens)

    # Send a provider request with retries for network and temporary provider failures.
    async def _request_with_retries(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        # Calculate the total number of attempts including the first request.
        attempts = self.settings.llm_max_retries + 1
        # Run each allowed request attempt.
        for attempt in range(attempts):
            # Try the provider request for this attempt.
            try:
                # Send the HTTP request through the reusable client.
                response = await self._client.request(method, path, **kwargs)
                # Convert a successful HTTP response into JSON or raise a typed error.
                return self._handle_response(response)
            # Do not retry invalid API keys because retrying cannot fix credentials.
            except LLMAuthError:
                # Re-raise the auth error exactly as-is.
                raise
            # Retry timeouts and network failures while attempts remain.
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                # Stop retrying after the last attempt.
                if attempt == attempts - 1:
                    # Raise a frontend-safe provider unreachable error.
                    raise LLMError("LLM provider is unreachable.") from exc
                # Wait a little longer after each failed attempt.
                await asyncio.sleep(0.5 * (attempt + 1))
            # Retry temporary LLM errors while attempts remain.
            except LLMError:
                # Stop retrying after the last attempt.
                if attempt == attempts - 1:
                    # Re-raise the final LLM error.
                    raise
                # Wait a little longer after each failed attempt.
                await asyncio.sleep(0.5 * (attempt + 1))
        # Raise a fallback error if the loop ends unexpectedly.
        raise LLMError("LLM provider request failed.")

    # Translate an HTTP response into provider JSON or a typed LLM exception.
    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        # Treat HTTP 401 as a clear invalid API key problem.
        if response.status_code == 401:
            # Raise the auth-specific error used by API routes.
            raise LLMAuthError("Invalid API Key")
        # Treat rate limits and server errors as temporary provider failures.
        if response.status_code == 429 or response.status_code >= 500:
            # Raise a retryable LLM error.
            raise LLMError(f"LLM provider temporarily unavailable ({response.status_code}).")
        # Treat other 4xx responses as rejected requests.
        if response.status_code >= 400:
            # Extract a useful provider error message when possible.
            detail = self._provider_error_detail(response)
            # Raise a clear rejected-request error.
            raise LLMError(f"LLM provider rejected the request ({response.status_code}): {detail}")
        # Try to parse the successful provider response as JSON.
        try:
            # Return the decoded provider response.
            return response.json()
        # Convert invalid JSON into a controlled LLM error.
        except ValueError as exc:
            # Raise a frontend-safe JSON parsing failure.
            raise LLMError("LLM provider returned invalid JSON.") from exc

    # Extract the best provider error message from a failed HTTP response.
    @staticmethod
    # Define this as static because it only uses the response argument.
    def _provider_error_detail(response: httpx.Response) -> str:
        # Try to parse the provider error body as JSON.
        try:
            # Decode the provider response body.
            body = response.json()
        # Fall back to plain text when the body is not JSON.
        except ValueError:
            # Return the first part of the raw response text.
            return response.text[:300]
        # Read the common provider error field.
        error = body.get("error")
        # Handle provider errors shaped like {"error": {"message": "..."} }.
        if isinstance(error, dict):
            # Read the nested message value.
            message = error.get("message")
            # Return the nested message when it is text.
            if isinstance(message, str):
                # Return the provider message.
                return message
        # Handle provider errors shaped like {"error": "..."}.
        if isinstance(error, str):
            # Return the error string directly.
            return error
        # Return a fallback when the provider error shape is unknown.
        return "Unknown provider error."

    # Extract assistant text from an OpenAI-compatible chat completion response.
    @staticmethod
    # Define this as static because it only uses the response argument.
    def _extract_text(response: dict[str, Any]) -> str:
        # Read the choices array from the provider response.
        choices = response.get("choices", [])
        # Return an empty message when the provider returned no choices.
        if not choices:
            # Return an empty string because there is no assistant content.
            return ""
        # Read the message object from the first choice.
        message = choices[0].get("message", {})
        # Read the content field from the message object.
        content = message.get("content", "")
        # Return the content when it is text.
        if isinstance(content, str):
            # Return the assistant message text.
            return content
        # Return an empty string when content is not a simple string.
        return ""


# Define a dict wrapper that keeps unresolved prompt placeholders instead of crashing.
class SafePromptValues(dict[str, Any]):
    # Return a placeholder string when a prompt key is missing.
    def __missing__(self, key: str) -> str:
        # Reconstruct the original placeholder text.
        return "{" + key + "}"


# Cache settings so the app reads environment configuration once.
@lru_cache(maxsize=1)
# Return the singleton Settings object.
def get_settings() -> Settings:
    # Create the typed settings object from environment variables and .env.
    return Settings()


# Create the global LLM readiness status object.
_status = LLMStatus()
# Store the global singleton LLM connector.
_connector: LLMConnector | None = None
# Create a lock so singleton connector creation is safe.
_connector_lock = Lock()


# Return the current LLM readiness status.
def get_llm_status() -> LLMStatus:
    # Return the global status object.
    return _status


# Return the singleton LLM connector, creating it the first time it is needed.
def get_llm_connector() -> LLMConnector:
    # Declare that this function writes the module-level connector variable.
    global _connector
    # Check whether a connector has already been created.
    if _connector is None:
        # Lock connector creation so concurrent requests do not create duplicates.
        with _connector_lock:
            # Check again inside the lock in case another thread created it first.
            if _connector is None:
                # Create the connector from the cached settings.
                _connector = LLMConnector(get_settings())
    # Return the ready connector instance.
    return _connector


# Set up the LLM connection during FastAPI startup.
async def setup_llm_connection() -> LLMStatus:
    # Read the cached settings for provider metadata.
    settings = get_settings()
    # Store the configured provider name in the global status.
    _status.provider = settings.llm_provider
    # Store the configured model name in the global status.
    _status.model = settings.llm_model_name
    # Try to initialize the singleton connector.
    try:
        # Create the connector if needed and send the startup ping.
        await get_llm_connector().initialize()
    # Convert invalid credentials into a stable status message.
    except LLMAuthError:
        # Mark the LLM as not ready.
        _status.ready = False
        # Store the exact frontend-facing auth error.
        _status.error = "Invalid API Key"
        # Log the auth failure without printing the key.
        logger.error("LLM setup failed: Invalid API Key")
    # Convert configuration and provider failures into a stable status message.
    except (LLMConfigError, LLMError) as exc:
        # Mark the LLM as not ready.
        _status.ready = False
        # Store the error text for the status endpoint.
        _status.error = str(exc)
        # Log the setup failure.
        logger.error("LLM setup failed: %s", exc)
    # Handle successful initialization.
    else:
        # Mark the LLM as ready.
        _status.ready = True
        # Clear any previous setup error.
        _status.error = None
    # Return the updated status object.
    return _status


# Close the singleton LLM connector during FastAPI shutdown.
async def close_llm_connection() -> None:
    # Declare that this function writes the module-level connector variable.
    global _connector
    # Lock connector cleanup so shutdown cannot race with creation.
    with _connector_lock:
        # Copy the connector reference before clearing it.
        connector = _connector
        # Clear the global connector reference.
        _connector = None
    # Close the connector only if one was created.
    if connector is not None:
        # Close the connector's underlying HTTP client.
        await connector.close()
