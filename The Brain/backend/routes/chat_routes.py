"""This file exposes chat-related FastAPI endpoints."""

# Import Any so JSON response payloads can be typed.
from typing import Any

# Import FastAPI tools for route registration and controlled HTTP errors.
from fastapi import APIRouter, HTTPException
# Import StreamingResponse so chat answers can stream over SSE.
from fastapi.responses import StreamingResponse

# Import shared LLM exceptions so route handlers return frontend-clear HTTP errors.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError
# Import request schemas for chat endpoints.
from backend.schemas import ChatRequest, RoutedChatRequest
# Import chat service functions that own business logic.
from backend.services.chat_service import answer_chat, answer_routed_chat, build_routed_chat_stream
# Import SSE helpers for streaming responses.
from backend.services.streaming_service import make_sse_response, stream_llm_response

# Create the router mounted by main.py.
router = APIRouter()


# Register the generic chat endpoint.
@router.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    # Convert LLM errors into clear HTTP responses.
    try:
        # Generate the basic chat response.
        return await answer_chat(request.prompt)
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


# Register the dynamic model routed chat endpoint.
@router.post("/api/chat/routed")
async def chat_routed(request: RoutedChatRequest) -> dict[str, Any]:
    # Convert routing and LLM errors into clear HTTP responses.
    try:
        # Generate a routed chat response with compact routing metadata.
        return await answer_routed_chat(request.prompt, request.light_model_name, request.heavy_model_name, request.classifier_model_name, request.fallback_model_name)
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


# Register the streaming chat endpoint.
@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    # Build the OpenAI-compatible messages for the simple chat request.
    messages = [{"role": "user", "content": request.prompt}]
    # Return the SSE stream with hardcoded LLM settings.
    return make_sse_response(stream_llm_response(messages=messages, max_tokens=800))


# Register the dynamic model routed streaming chat endpoint.
@router.post("/api/chat/routed/stream")
async def chat_routed_stream(request: RoutedChatRequest) -> StreamingResponse:
    # Convert routing errors into clear HTTP responses before the stream starts.
    try:
        # Build messages, selected model, and start metadata for routed streaming.
        messages, selected_model, start_data = await build_routed_chat_stream(request.prompt, request.light_model_name, request.heavy_model_name, request.classifier_model_name)
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
    return make_sse_response(stream_llm_response(messages=messages, max_tokens=800, model_name=selected_model, start_data=start_data))
