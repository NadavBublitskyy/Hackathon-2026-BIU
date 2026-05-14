"""This file owns dynamic model routing and fallback answer generation."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import logging so model fallback decisions can be logged.
import logging
# Import Any so compact response payloads can include endpoint-specific metadata.
from typing import Any

# Import the singleton connector and result type used for final answer generation.
from backend.llm_client import LLMResult, get_llm_connector
# Import shared LLM exceptions so auth/config errors are not hidden by fallback behavior.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError
# Import the model matching class from the orchestrator package.
from backend.orchestrator.match_model import MatchModel, MatchModelResult

# Create a logger for fallback routing decisions.
logger = logging.getLogger(__name__)


# Route a user prompt to either the light or heavy model.
async def route_prompt_to_model(prompt: str, light_model_name: str, heavy_model_name: str, classifier_model_name: str) -> MatchModelResult:
    # Create the router around the existing singleton LLM connector.
    router = MatchModel(get_llm_connector(), classifier_model_name=classifier_model_name)
    # Ask the router to choose the best answer model.
    return await router.choose_model(prompt, light_model_name, heavy_model_name, classifier_model_name=classifier_model_name)


# Send final answer messages with the selected model and optional fallback.
async def send_messages_with_model_fallback(messages: list[dict[str, str]], selected_model: str, fallback_model_name: str | None, max_tokens: int) -> tuple[LLMResult, str, bool]:
    # Try the model selected by MatchModel first.
    try:
        # Send the request using the selected answer model.
        result = await get_llm_connector().send_messages(messages=messages, temperature=0.2, max_tokens=max_tokens, model_name=selected_model)
        # Return the result, the actual answering model, and the fallback flag.
        return result, selected_model, False
    # Do not hide invalid API keys or broken local configuration behind fallback behavior.
    except (LLMAuthError, LLMConfigError):
        # Re-raise these errors so route handlers can return the correct HTTP status.
        raise
    # Retry with the fallback model when the selected provider model fails.
    except LLMError as exc:
        # Re-raise the original failure when no different fallback model was supplied.
        if not fallback_model_name or fallback_model_name == selected_model:
            # Preserve the original provider error.
            raise
        # Log the provider/model fallback without exposing secrets.
        logger.warning("Selected model %s failed, retrying with fallback model %s: %s", selected_model, fallback_model_name, exc)
        # Send the same messages through the fallback answer model.
        fallback_result = await get_llm_connector().send_messages(messages=messages, temperature=0.2, max_tokens=max_tokens, model_name=fallback_model_name)
        # Return the fallback result and mark fallback as used.
        return fallback_result, fallback_model_name, True


# Convert a routed LLM result into the compact API response shape.
def routed_response_payload(result: LLMResult, route: MatchModelResult, answered_by_model: str, fallback_used: bool, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    # Start with the core routed response fields.
    payload = {
        "response": result.message,
        "selected_model": route.selected_model,
        "answered_by_model": answered_by_model,
        "difficulty": route.difficulty,
        "classifier_model": route.classifier_model,
        "classification_ms": round(route.classification_ms, 2),
        "fallback_used": fallback_used,
    }
    # Add endpoint-specific fields such as path verification when needed.
    if extra:
        # Merge the extra fields into the response object.
        payload.update(extra)
    # Return the complete response payload.
    return payload
