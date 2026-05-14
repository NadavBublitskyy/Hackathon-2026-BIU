"""This file exposes The Brain service as a FastAPI API."""

# Import json so uploaded context files can be decoded.
import json
# Import logging so route failures can be written to the backend logs.
import logging
# Import asynccontextmanager so FastAPI can run setup and cleanup code.
from contextlib import asynccontextmanager
# Import Any and AsyncIterator so responses and SSE generators can be typed.
from typing import Any, AsyncIterator

# Import FastAPI tools for routes, uploaded files, form fields, and controlled HTTP errors.
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
# Import CORS middleware so the frontend can call this backend from the browser.
from fastapi.middleware.cors import CORSMiddleware
# Import StreamingResponse so tokens can be sent to clients as Server-Sent Events.
from fastapi.responses import StreamingResponse
# Import Pydantic tools so request bodies can be validated.
from pydantic import BaseModel, Field

# Import the attribution verifier that checks LLM-mentioned paths against structure.json.
from backend.code_attribution import CodeAttributionVerifier
# Import context-aware prompt helpers for the /api/blueprint endpoint.
from backend.llm_blueprint import build_context_aware_messages, build_context_debug_prompt
# Import LLM setup, connector, settings, and error types from the setup module.
from backend.setup import LLMAuthError, LLMConfigError, LLMError, close_llm_connection, get_llm_connector, get_llm_status, get_settings, setup_llm_connection

# Configure the process-wide logging format.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Create a logger for this API module.
logger = logging.getLogger(__name__)


# Define the request body accepted by /api/chat.
class ChatRequest(BaseModel):
    # Store only the user's prompt so the Swagger form stays simple.
    prompt: str = Field(min_length=1)


# Read and parse a JSON upload from Swagger or the frontend.
async def read_json_upload(upload: UploadFile) -> Any:
    # Read the uploaded file bytes.
    content = await upload.read()
    # Try to parse the uploaded bytes as JSON.
    try:
        # Decode the JSON payload into Python objects.
        return json.loads(content)
    # Convert invalid JSON into a clear HTTP 400 response.
    except json.JSONDecodeError as exc:
        # Tell the caller which uploaded file was invalid.
        raise HTTPException(status_code=400, detail=f"{upload.filename or 'uploaded file'} is not valid JSON.") from exc


# Format one Server-Sent Event frame.
def sse_event(event: str, data: dict[str, Any]) -> str:
    # Encode the event data as compact JSON for browser EventSource or fetch readers.
    payload = json.dumps(data, ensure_ascii=False)
    # Return a complete SSE frame.
    return f"event: {event}\ndata: {payload}\n\n"


# Stream LLM tokens as SSE frames.
async def stream_llm_response(messages: list[dict[str, str]], max_tokens: int) -> AsyncIterator[str]:
    # Send a first event immediately so clients can confirm the stream opened.
    yield sse_event("start", {"status": "streaming"})
    # Convert LLM errors into SSE error events.
    try:
        # Stream provider tokens through the singleton LLM connector.
        async for token in get_llm_connector().stream_messages(messages=messages, temperature=0.2, max_tokens=max_tokens):
            # Yield each token as soon as it arrives.
            yield sse_event("token", {"token": token})
    # Convert provider 401 errors into a frontend-clear stream error.
    except LLMAuthError:
        # Yield an auth error event without exposing the key.
        yield sse_event("error", {"detail": "Invalid API Key"})
        # Stop the stream after the error.
        return
    # Convert local configuration errors into a stream error.
    except LLMConfigError as exc:
        # Yield a config error event.
        yield sse_event("error", {"detail": str(exc)})
        # Stop the stream after the error.
        return
    # Convert provider/network failures into a stream error.
    except LLMError as exc:
        # Log the streaming failure for debugging.
        logger.warning("LLM stream failed: %s", exc)
        # Yield a provider error event.
        yield sse_event("error", {"detail": str(exc)})
        # Stop the stream after the error.
        return
    # Yield a final event so clients know the markdown stream is complete.
    yield sse_event("done", {"done": True})


# Build the standard SSE response with headers that discourage proxy buffering.
def make_sse_response(stream: AsyncIterator[str]) -> StreamingResponse:
    # Return a FastAPI StreamingResponse for Server-Sent Events.
    return StreamingResponse(stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Define the FastAPI lifespan hook that connects and disconnects the LLM client.
@asynccontextmanager
# Run startup setup before requests and cleanup after shutdown.
async def lifespan(app: FastAPI):
    # Initialize the LLM connection and run the startup ping.
    await setup_llm_connection()
    # Yield control back to FastAPI so the app can serve requests.
    yield
    # Close the LLM connection when the app shuts down.
    await close_llm_connection()


# Load runtime settings once for app creation and middleware setup.
settings = get_settings()
# Create the FastAPI application object.
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Add CORS middleware so configured frontend origins can call this API.
app.add_middleware(
    # Use FastAPI's standard CORS middleware class.
    CORSMiddleware,
    # Allow only the origins configured in settings.
    allow_origins=settings.cors_origins,
    # Allow cookies and authorization headers when needed.
    allow_credentials=True,
    # Allow all HTTP methods for the API.
    allow_methods=["*"],
    # Allow all request headers for the API.
    allow_headers=["*"],
# Close the middleware call.
)


# Register the endpoint that reports whether the LLM client is ready.
@app.get("/api/llm/status")
# Return provider and model status for the frontend.
async def llm_status() -> dict[str, Any]:
    # Read the current LLM startup status.
    state = get_llm_status()
    # Return an error response if the startup ping did not succeed.
    if not state.ready:
        # Return a 401 when the provider rejected the API key.
        if state.error == "Invalid API Key":
            # Raise a frontend-clear invalid key response.
            raise HTTPException(status_code=401, detail="Invalid API Key")
        # Raise a service unavailable response for other setup failures.
        raise HTTPException(status_code=503, detail=state.error or "LLM client is not ready")
    # Return a ready response when the LLM startup ping succeeded.
    return {"status": "ready", "provider": state.provider, "model": state.model}


# Register the generic chat endpoint.
@app.post("/api/chat")
# Send validated chat messages to the configured LLM provider.
async def chat(request: ChatRequest) -> dict[str, Any]:
    # Convert LLM errors into clear HTTP responses.
    try:
        # Send the request messages through the singleton LLM connector.
        result = await get_llm_connector().send_messages(messages=[{"role": "user", "content": request.prompt}], temperature=0.2, max_tokens=800)
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
        # Log the LLM request failure for debugging.
        logger.warning("LLM request failed: %s", exc)
        # Raise a 502 response with a safe error message.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Return only the extracted LLM response text.
    return {"response": result.message}


# Register the streaming chat endpoint.
@app.post("/api/chat/stream")
# Stream chat response tokens for a simple user prompt.
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    # Build the OpenAI-compatible messages for the simple chat request.
    messages = [{"role": "user", "content": request.prompt}]
    # Return the SSE stream with hardcoded LLM settings.
    return make_sse_response(stream_llm_response(messages=messages, max_tokens=800))


# Register the implementation blueprint endpoint.
@app.post("/api/blueprint")
# Use the context-aware prompt builder to answer a repo question from structure and snippets.
async def blueprint(prompt: str = Form(..., min_length=1), structure_json: UploadFile = File(...), relevant_context_json: UploadFile = File(...)) -> dict[str, Any]:
    # Parse the uploaded structure.json file.
    structure_data = await read_json_upload(structure_json)
    # Parse the uploaded relevant_context JSON file.
    relevant_context_data = await read_json_upload(relevant_context_json)
    # Build the exact message payload sent to the LLM.
    messages = build_context_aware_messages(prompt, structure_data, relevant_context_data)
    # Build a readable debug prompt that shows all three context layers.
    generated_prompt = build_context_debug_prompt(prompt, structure_data, relevant_context_data)
    # Log the generated prompt so debugging can inspect system, structure, snippets, and user query.
    logger.info("Generated context-aware prompt:\n%s", generated_prompt)
    # Convert LLM errors into clear HTTP responses.
    try:
        # Send the assembled context-aware messages to the LLM with hardcoded settings.
        result = await get_llm_connector().send_messages(messages=messages, temperature=0.2, max_tokens=1200)
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
        # Log the LLM blueprint failure for debugging.
        logger.warning("LLM blueprint request failed: %s", exc)
        # Raise a 502 response with a safe error message.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # Verify that every file path mentioned by the LLM exists in structure.json.
    paths_verified = CodeAttributionVerifier.verify_response_paths(structure_data, result.message)
    # Return the LLM response text and the grounding verification result.
    return {"response": result.message, "paths_verified": paths_verified}


# Register the streaming context-aware blueprint endpoint.
@app.post("/api/blueprint/stream")
# Stream context-aware response tokens from uploaded structure and relevant context JSON files.
async def blueprint_stream(prompt: str = Form(..., min_length=1), structure_json: UploadFile = File(...), relevant_context_json: UploadFile = File(...)) -> StreamingResponse:
    # Parse the uploaded structure.json file.
    structure_data = await read_json_upload(structure_json)
    # Parse the uploaded relevant_context JSON file.
    relevant_context_data = await read_json_upload(relevant_context_json)
    # Build the exact message payload sent to the LLM.
    messages = build_context_aware_messages(prompt, structure_data, relevant_context_data)
    # Build a readable debug prompt that shows all three context layers.
    generated_prompt = build_context_debug_prompt(prompt, structure_data, relevant_context_data)
    # Log the generated prompt so debugging can inspect system, structure, snippets, and user query.
    logger.info("Generated streaming context-aware prompt:\n%s", generated_prompt)
    # Return the SSE stream with hardcoded LLM settings.
    return make_sse_response(stream_llm_response(messages=messages, max_tokens=1200))
