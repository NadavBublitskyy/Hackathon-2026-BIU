"""This file defines request models shared by FastAPI routes."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import Pydantic tools so request bodies can be validated.
from pydantic import BaseModel, Field

# Import the default classifier model from the router implementation.
from backend.orchestrator.match_model import DEFAULT_CLASSIFIER_MODEL_NAME

# Define the request body accepted by /api/chat.
class ChatRequest(BaseModel):
    # Store only the user's prompt so the Swagger form stays simple.
    prompt: str = Field(min_length=1)


# Define the request body accepted by /api/chat/routed.
class RoutedChatRequest(BaseModel):
    # Store the user's prompt that should be routed and answered.
    prompt: str = Field(min_length=1)
    # Omit to let the backend resolve from LLM_MODEL_NAME; provide to override.
    light_model_name: str | None = Field(default=None)
    # Omit to let the backend resolve from LLM_MODEL_NAME; provide to override.
    heavy_model_name: str | None = Field(default=None)
    # Store the cheap classifier model that decides between the light and heavy models.
    classifier_model_name: str = Field(default=DEFAULT_CLASSIFIER_MODEL_NAME, min_length=1)
    # Store an optional fallback model for final answer generation if the selected model fails.
    fallback_model_name: str | None = Field(default=None)


# Define the request body accepted by /api/ingest.
class IngestRequest(BaseModel):
    # Store the public GitHub repository URL to index.
    github_url: str = Field(min_length=1)


# Define the request body accepted by /api/memory/retrieve.
class MemoryRetrieveRequest(BaseModel):
    # Store the user's original query.
    user_query: str | None = Field(default=None)
    # Store the alternate prompt key used by the frontend.
    prompt: str | None = Field(default=None)
    # Store an optional selected graph file path for focused retrieval.
    selected_file_path: str | None = Field(default=None)
    # Store the structure JSON produced by /api/ingest.
    structure_json: dict | None = Field(default=None)
    # Store the code chunks JSON produced by /api/ingest.
    code_chunks_json: list[dict] = Field(default_factory=list)
    # Store an optional snippet limit. None means return all positively scored snippets.
    top_k: int | None = Field(default=None, ge=1)


# Define the request body accepted by /api/prompt/classify.
class PromptClassifyRequest(BaseModel):
    # Store the user's prompt that needs a routing category.
    prompt: str = Field(min_length=1)
    # Store an optional selected file path from the graph.
    selected_file_path: str | None = Field(default=None)
    # Store lightweight Memory candidates so classification can be biased by repo evidence.
    retrieved_context: list[dict] = Field(default_factory=list)
    # Store the cheap classifier model used for the category decision.
    classifier_model_name: str = Field(default=DEFAULT_CLASSIFIER_MODEL_NAME, min_length=1)
