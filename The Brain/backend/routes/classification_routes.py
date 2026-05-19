"""This file exposes LLM-based prompt classification endpoints."""

# Import asdict so dataclass results can be returned as JSON dictionaries.
from dataclasses import asdict
# Import Any so JSON response payloads can be typed.
from typing import Any

# Import FastAPI tools for route registration and controlled HTTP errors.
from fastapi import APIRouter, HTTPException

# Import shared LLM exceptions so route handlers return frontend-clear HTTP errors.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError
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
    try:
        result = await classify_prompt(request.prompt, request.selected_file_path, request.classifier_model_name, request.retrieved_context, request.repo_session_id)
    # Convert provider 401 errors into a frontend-clear response.
    except LLMAuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid API Key") from exc
    # Convert local configuration errors into a service unavailable response.
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Convert provider/network failures into a bad gateway response.
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Return a JSON-serializable dictionary.
    return asdict(result)
