"""This file exposes context-aware blueprint FastAPI endpoints."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import Any so JSON response payloads can be typed.
from typing import Any

# Import FastAPI tools for route registration, uploads, form fields, and controlled HTTP errors..
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
# Import StreamingResponse so blueprint answers can stream over SSE.
from fastapi.responses import StreamingResponse

# Import shared LLM exceptions so route handlers return frontend-clear HTTP errors.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError
# Import model defaults used by routed blueprint form fields.
from backend.schemas import DEFAULT_HEAVY_MODEL_NAME, DEFAULT_LIGHT_MODEL_NAME
# Import the default classifier model from the router implementation.
from backend.orchestrator.match_model import DEFAULT_CLASSIFIER_MODEL_NAME
# Import blueprint service functions that own business logic.
from backend.services.blueprint_service import answer_blueprint, answer_routed_blueprint, build_blueprint_stream, build_routed_blueprint_stream
# Import JSON upload parsing from its dedicated service.
from backend.services.json_upload_service import read_json_upload
# Import SSE helpers for streaming responses.
from backend.services.streaming_service import make_sse_response, stream_llm_response

# Create the router mounted by main.py.
router = APIRouter()


# Register the implementation blueprint endpoint.
@router.post("/api/blueprint")
async def blueprint(prompt: str = Form(..., min_length=1), structure_json: UploadFile = File(...), relevant_context_json: UploadFile = File(...)) -> dict[str, Any]:
    # Parse the uploaded structure.json file.
    structure_data = await read_json_upload(structure_json)
    # Parse the uploaded relevant_context JSON file.
    relevant_context_data = await read_json_upload(relevant_context_json)
    # Convert LLM errors into clear HTTP responses.
    try:
        # Generate a context-aware repo answer.
        return await answer_blueprint(prompt, structure_data, relevant_context_data)
    # Convert provider 401 errors into a frontend-clear response.
    except LLMAuthError as exc:
        # Raise a 401 response without exposing the key.
        raise HTTPException(status_code=401, detail="Invalid API Key") from exc
    # Convert local configuration errors into a service unavailable response.
    except LLMConfigError as exc:
        # Raise a 503 response with the configuration problem.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Convert provider/network failures into a bad gateway response.
    except LLMError as exc:
        # Raise a 502 response with a safe error message.
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# Register the routed implementation blueprint endpoint.
@router.post("/api/blueprint/routed")
async def blueprint_routed(
    prompt: str = Form(..., min_length=1),
    structure_json: UploadFile = File(...),
    relevant_context_json: UploadFile = File(...),
    light_model_name: str = Form(DEFAULT_LIGHT_MODEL_NAME, min_length=1),
    heavy_model_name: str = Form(DEFAULT_HEAVY_MODEL_NAME, min_length=1),
    classifier_model_name: str = Form(DEFAULT_CLASSIFIER_MODEL_NAME, min_length=1),
    fallback_model_name: str | None = Form(None),
) -> dict[str, Any]:
    # Parse the uploaded structure.json file.
    structure_data = await read_json_upload(structure_json)
    # Parse the uploaded relevant_context JSON file.
    relevant_context_data = await read_json_upload(relevant_context_json)
    # Convert routing and LLM errors into clear HTTP responses.
    try:
        # Generate a routed context-aware repo answer.
        return await answer_routed_blueprint(prompt, structure_data, relevant_context_data, light_model_name, heavy_model_name, classifier_model_name, fallback_model_name)
    # Convert provider 401 errors into a frontend-clear response.
    except LLMAuthError as exc:
        # Raise a 401 response without exposing the key.
        raise HTTPException(status_code=401, detail="Invalid API Key") from exc
    # Convert local configuration errors into a service unavailable response.
    except LLMConfigError as exc:
        # Raise a 503 response with the configuration problem.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Convert provider/network failures into a bad gateway response.
    except LLMError as exc:
        # Raise a 502 response with a safe error message.
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# Register the streaming context-aware blueprint endpoint.
@router.post("/api/blueprint/stream")
async def blueprint_stream(prompt: str = Form(..., min_length=1), structure_json: UploadFile = File(...), relevant_context_json: UploadFile = File(...)) -> StreamingResponse:
    # Parse the uploaded structure.json file.
    structure_data = await read_json_upload(structure_json)
    # Parse the uploaded relevant_context JSON file.
    relevant_context_data = await read_json_upload(relevant_context_json)
    # Build the exact message payload sent to the LLM.
    messages = build_blueprint_stream(prompt, structure_data, relevant_context_data)
    # Return the SSE stream with hardcoded LLM settings.
    return make_sse_response(stream_llm_response(messages=messages, max_tokens=500))


# Register the routed streaming context-aware blueprint endpoint.
@router.post("/api/blueprint/routed/stream")
async def blueprint_routed_stream(
    prompt: str = Form(..., min_length=1),
    structure_json: UploadFile = File(...),
    relevant_context_json: UploadFile = File(...),
    light_model_name: str = Form(DEFAULT_LIGHT_MODEL_NAME, min_length=1),
    heavy_model_name: str = Form(DEFAULT_HEAVY_MODEL_NAME, min_length=1),
    classifier_model_name: str = Form(DEFAULT_CLASSIFIER_MODEL_NAME, min_length=1),
) -> StreamingResponse:
    # Parse the uploaded structure.json file.
    structure_data = await read_json_upload(structure_json)
    # Parse the uploaded relevant_context JSON file.
    relevant_context_data = await read_json_upload(relevant_context_json)
    # Convert routing errors into clear HTTP responses before the stream starts.
    try:
        # Build messages, selected model, and start metadata for routed streaming.
        messages, selected_model, start_data = await build_routed_blueprint_stream(prompt, structure_data, relevant_context_data, light_model_name, heavy_model_name, classifier_model_name)
    # Convert provider 401 errors into a frontend-clear response.
    except LLMAuthError as exc:
        # Raise a 401 response without exposing the key.
        raise HTTPException(status_code=401, detail="Invalid API Key") from exc
    # Convert local configuration errors into a service unavailable response.
    except LLMConfigError as exc:
        # Raise a 503 response with the configuration problem.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Convert provider/network failures into a bad gateway response.
    except LLMError as exc:
        # Raise a 502 response with a safe error message.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Return the SSE stream using the selected model.
    return make_sse_response(stream_llm_response(messages=messages, max_tokens=500, model_name=selected_model, start_data=start_data))
