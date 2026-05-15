"""This file owns context-aware blueprint prompt execution and grounding checks."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import logging so generated prompts can be logged for debugging.
import logging
# Import Any so parsed JSON structures can be typed flexibly.
from typing import Any

# Import the singleton connector for non-routed blueprint calls.
from backend.llm_client import get_llm_connector
# Import path grounding verification from the orchestrator package.
from backend.orchestrator.code_attribution import CodeAttributionVerifier
# Import context-aware prompt helpers from the orchestrator package.
from backend.orchestrator.llm_blueprint import build_context_aware_messages, build_context_debug_prompt
# Import routing helpers for routed blueprint calls.
from backend.services.model_routing_service import routed_response_payload, route_prompt_to_model, send_messages_with_model_fallback

# Create a logger for generated prompt debugging.
logger = logging.getLogger(__name__)


# Build the context-aware messages and log the debug prompt.
def build_blueprint_messages(prompt: str, structure_data: Any, relevant_context_data: Any, log_label: str) -> list[dict[str, str]]:
    # Build the exact message payload sent to the LLM.
    messages = build_context_aware_messages(prompt, structure_data, relevant_context_data)
    # Build a readable debug prompt that shows all three context layers.
    generated_prompt = build_context_debug_prompt(prompt, structure_data, relevant_context_data)
    # Log the generated prompt so debugging can inspect system, structure, snippets, and user query.
    logger.info("%s:\n%s", log_label, generated_prompt)
    # Return the OpenAI-compatible messages.
    return messages




# Build route metadata for context-aware streaming without dynamic routing.
def build_blueprint_stream(prompt: str, structure_data: Any, relevant_context_data: Any) -> list[dict[str, str]]:
    # Build and log the context-aware messages for a streaming answer.
    return build_blueprint_messages(prompt, structure_data, relevant_context_data, "Generated streaming context-aware prompt")


# Build route metadata for routed context-aware streaming.
async def build_routed_blueprint_stream(prompt: str, structure_data: Any, relevant_context_data: Any, light_model_name: str, heavy_model_name: str, classifier_model_name: str) -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    # Build and log the context-aware messages for a routed streaming answer.
    messages = build_blueprint_messages(prompt, structure_data, relevant_context_data, "Generated routed streaming context-aware prompt")
    # Ask MatchModel to choose between the caller-provided light and heavy model names.
    route = await route_prompt_to_model(prompt, light_model_name, heavy_model_name, classifier_model_name)
    # Include routing metadata in the first SSE event.
    start_data = {"selected_model": route.selected_model, "answered_by_model": route.selected_model, "difficulty": route.difficulty, "classifier_model": route.classifier_model, "classification_ms": round(route.classification_ms, 2)}
    # Return the stream inputs to the route layer.
    return messages, route.selected_model, start_data
