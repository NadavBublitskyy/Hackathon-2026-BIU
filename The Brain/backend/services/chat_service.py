"""This file owns chat response generation without FastAPI route decorators."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import Any so JSON response payloads can be typed.
from typing import Any

# Import the singleton connector for normal chat calls.
from backend.llm_client import get_llm_connector
# Import routing helpers for routed chat calls.
from backend.services.model_routing_service import routed_response_payload, route_prompt_to_model, send_messages_with_model_fallback

# Build route metadata for routed chat streaming.
async def build_routed_chat_stream(prompt: str, light_model_name: str, heavy_model_name: str, classifier_model_name: str) -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    # Ask MatchModel to choose between the caller-provided light and heavy model names.
    route = await route_prompt_to_model(prompt, light_model_name, heavy_model_name, classifier_model_name)
    # Build the OpenAI-compatible messages for the simple chat request.
    messages = [{"role": "user", "content": prompt}]
    # Include routing metadata in the first SSE event.
    start_data = {"selected_model": route.selected_model, "answered_by_model": route.selected_model, "difficulty": route.difficulty, "classifier_model": route.classifier_model, "classification_ms": round(route.classification_ms, 2)}
    # Return the stream inputs to the route layer.
    return messages, route.selected_model, start_data
