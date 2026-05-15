"""This file exposes LLM-based prompt classification endpoints."""

# Import asdict so dataclass results can be returned as JSON dictionaries.
from dataclasses import asdict
# Import Any so JSON response payloads can be typed.
from typing import Any

# Import FastAPI tools for route registration.
from fastapi import APIRouter

# Import the request schema for prompt classification.
from backend.schemas import PromptClassifyRequest
# Import the LLM-based prompt classification service.
from backend.services.prompt_classification_service import classify_prompt

# Create the router mounted by main.py.
router = APIRouter()


# Register the endpoint that classifies a prompt into one frontend routing category.
@router.post("/api/prompt/classify")
async def classify_user_prompt(request: PromptClassifyRequest) -> dict[str, Any]:
    # Classify the prompt with the requested cheap classifier model.
    result = await classify_prompt(request.prompt, request.selected_file_path, request.classifier_model_name, request.retrieved_context)
    # Return a JSON-serializable dictionary.
    return asdict(result)
