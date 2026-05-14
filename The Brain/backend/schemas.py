"""This file defines request models shared by FastAPI routes."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import Pydantic tools so request bodies can be validated.
from pydantic import BaseModel, Field

# Import the default classifier model from the router implementation.
from backend.orchestrator.match_model import DEFAULT_CLASSIFIER_MODEL_NAME

# Define the default fast model suggestion for routed requests.
DEFAULT_LIGHT_MODEL_NAME = "meta-llama/llama-3-8b-instruct"
# Define the default stronger model suggestion for routed requests.
DEFAULT_HEAVY_MODEL_NAME = "openai/gpt-4o"


# Define the request body accepted by /api/chat.
class ChatRequest(BaseModel):
    # Store only the user's prompt so the Swagger form stays simple.
    prompt: str = Field(min_length=1)


# Define the request body accepted by /api/chat/routed.
class RoutedChatRequest(BaseModel):
    # Store the user's prompt that should be routed and answered.
    prompt: str = Field(min_length=1)
    # Store the cheap model name that should answer easy navigation questions.
    light_model_name: str = Field(default=DEFAULT_LIGHT_MODEL_NAME, min_length=1)
    # Store the stronger model name that should answer hard reasoning questions.
    heavy_model_name: str = Field(default=DEFAULT_HEAVY_MODEL_NAME, min_length=1)
    # Store the cheap classifier model that decides between the light and heavy models.
    classifier_model_name: str = Field(default=DEFAULT_CLASSIFIER_MODEL_NAME, min_length=1)
    # Store an optional fallback model for final answer generation if the selected model fails.
    fallback_model_name: str | None = Field(default=None)
