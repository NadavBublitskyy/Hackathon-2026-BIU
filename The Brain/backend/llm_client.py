"""This file owns the remote LLM client, singleton lifecycle, and provider requests."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import asyncio so retry waits can sleep without blocking FastAPI's event loop.
import asyncio
# Import json so streamed provider events can be decoded.
import json
# Import logging so startup and provider errors are written to the app logs.
import logging
# Import dataclass so simple result/status containers can be declared with less boilerplate.
from dataclasses import dataclass
# Import Lock so singleton client creation is thread-safe.
from threading import Lock
# Import Any and AsyncIterator so prompt values, raw responses, and token streams can be typed.
from typing import Any, AsyncIterator

# Import httpx so the service can call the OpenRouter/OpenAI-compatible HTTP API.
import httpx

# Import settings helpers from the dedicated configuration module.
from backend.config import Settings, get_settings
# Import shared LLM exceptions from the dedicated error module.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError

# Create a module logger so this file can report LLM setup results.
logger = logging.getLogger(__name__)


# Define a small result container for successful LLM responses.
@dataclass
class LLMResult:
    # Store the assistant text extracted from the provider response.
    message: str
    # Store the full provider response for debugging or advanced frontend use.
    raw: dict[str, Any]
    # Store the model that was requested for this response.
    model: str | None = None


# Define a small status container for startup readiness.
@dataclass
class LLMStatus:
    # Store whether the startup ping succeeded.
    ready: bool = False
    # Store a user-facing setup error when setup failed.
    error: str | None = None
    # Store the configured provider name.
    provider: str | None = None
    # Store the configured model name.
    model: str | None = None


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
            # Raise a configuration error that routes can return to the frontend.
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
    async def send_messages(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 800, model_name: str | None = None) -> LLMResult:
        # Choose the per-request model when one is provided, otherwise use the configured default model.
        selected_model = model_name or self.settings.llm_model_name
        # Build the OpenAI-compatible chat completion request body.
        payload = {"model": selected_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        # Send the request and retry transient provider failures.
        raw = await self._request_with_retries("POST", "/chat/completions", json=payload)
        # Return both the extracted text and the raw provider response.
        return LLMResult(message=self._extract_text(raw), raw=raw, model=selected_model)

    # Stream an already-built list of chat messages and yield text tokens as they arrive.
    async def stream_messages(self, messages: list[dict[str, str]], temperature: float = 0.2, max_tokens: int = 800, model_name: str | None = None) -> AsyncIterator[str]:
        # Choose the per-request model when one is provided, otherwise use the configured default model.
        selected_model = model_name or self.settings.llm_model_name
        # Build the OpenAI-compatible streaming chat completion request body.
        payload = {"model": selected_model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": True}
        # Open a streaming HTTP response from the LLM provider.
        async with self._client.stream("POST", "/chat/completions", json=payload) as response:
            # Validate the streaming HTTP status before reading tokens.
            await self._raise_for_stream_status(response)
            # Iterate over the provider's Server-Sent Event lines.
            async for line in response.aiter_lines():
                # Ignore empty heartbeat or separator lines.
                if not line:
                    # Continue to the next streamed line.
                    continue
                # Ignore non-data SSE fields.
                if not line.startswith("data:"):
                    # Continue to the next streamed line.
                    continue
                # Remove the SSE data prefix.
                data = line.removeprefix("data:").strip()
                # Stop when the provider marks the stream as finished.
                if data == "[DONE]":
                    # End the token generator.
                    break
                # Convert the provider event JSON into a Python dictionary.
                event = self._parse_stream_event(data)
                # Extract the next content token from the event.
                token = self._extract_stream_token(event)
                # Yield non-empty tokens to the FastAPI SSE response.
                if token:
                    # Send the token to the caller immediately.
                    yield token

    # Fill a human prompt template, wrap it with a system prompt, and send both to the LLM.
    async def send_message_to_llm_wrapped_by(self, system_prompt: str, human_prompt_template: str, values: dict[str, Any] | None = None, temperature: float = 0.2, max_tokens: int = 1200, model_name: str | None = None) -> LLMResult:
        # Convert prompt values into a safe dict that leaves missing placeholders visible.
        prompt_values = SafePromptValues(values or {})
        # Format the human prompt with the provided values.
        human_prompt = human_prompt_template.format_map(prompt_values)
        # Send the wrapped system and human messages to the provider.
        return await self.send_messages(messages=[{"role": "system", "content": system_prompt.strip()}, {"role": "user", "content": human_prompt.strip()}], temperature=temperature, max_tokens=max_tokens, model_name=model_name)

    # Validate the HTTP status for a streaming provider response.
    async def _raise_for_stream_status(self, response: httpx.Response) -> None:
        # Treat HTTP 401 as a clear invalid API key problem.
        if response.status_code == 401:
            # Raise the auth-specific error used by API routes.
            raise LLMAuthError("Invalid API Key")
        # Return immediately when the provider accepted the stream request.
        if response.status_code < 400:
            # No error handling is needed for successful status codes.
            return
        # Read the response body so provider error details are not lost.
        body = (await response.aread()).decode("utf-8", errors="replace")
        # Treat rate limits and server errors as temporary provider failures.
        if response.status_code == 429 or response.status_code >= 500:
            # Raise a retryable LLM error.
            raise LLMError(f"LLM provider temporarily unavailable ({response.status_code}).")
        # Extract a readable provider error message.
        detail = self._provider_error_detail_from_text(body)
        # Raise a clear rejected-request error.
        raise LLMError(f"LLM provider rejected the request ({response.status_code}): {detail}")

    # Parse one provider SSE data line into a dictionary.
    def _parse_stream_event(self, data: str) -> dict[str, Any]:
        # Try to decode the event JSON.
        try:
            # Return the decoded event object.
            event = json.loads(data)
        # Convert invalid provider JSON into a controlled LLM error.
        except json.JSONDecodeError as exc:
            # Raise a frontend-safe parsing failure.
            raise LLMError("LLM provider returned invalid stream JSON.") from exc
        # Detect provider error events inside the stream.
        if isinstance(event, dict) and event.get("error"):
            # Raise the provider error as an LLM failure.
            raise LLMError(str(event["error"]))
        # Return valid provider events.
        return event

    # Extract one text token from a streaming OpenAI-compatible event.
    @staticmethod
    def _extract_stream_token(event: dict[str, Any]) -> str:
        # Read the choices array from the provider stream event.
        choices = event.get("choices", [])
        # Return an empty token when no choices were streamed.
        if not choices:
            # Return an empty string because there is no delta content.
            return ""
        # Read the delta object from the first streamed choice.
        delta = choices[0].get("delta", {})
        # Read the text token from the delta object.
        content = delta.get("content", "")
        # Return the content when it is text.
        if isinstance(content, str):
            # Return the streamed token.
            return content
        # Return an empty string when the delta content is not plain text.
        return ""

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

    # Extract the best provider error message from a raw response body.
    @staticmethod
    def _provider_error_detail_from_text(response_text: str) -> str:
        # Try to parse the raw provider error text as JSON.
        try:
            # Decode the raw provider error text.
            body = json.loads(response_text)
        # Fall back to plain text when the body is not JSON.
        except ValueError:
            # Return the first part of the raw response text.
            return response_text[:300]
        # Read the common provider error field.
        error = body.get("error") if isinstance(body, dict) else None
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
