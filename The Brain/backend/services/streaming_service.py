"""This file owns Server-Sent Events formatting and LLM token streaming."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import json so SSE payloads can be serialized.
import json
# Import logging so streaming failures can be logged.
import logging
# Import AsyncIterator so async token streams can be typed.
from typing import Any, AsyncIterator

# Import StreamingResponse so tokens can be sent to clients as Server-Sent Events.
from fastapi.responses import StreamingResponse

# Import the singleton connector used to stream provider tokens.
from backend.llm_client import get_llm_connector
# Import shared LLM exceptions so stream failures become SSE error frames.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError

# Create a logger for streaming failures.
logger = logging.getLogger(__name__)


# Format one Server-Sent Event frame.
def sse_event(event: str, data: dict[str, Any]) -> str:
    # Encode the event data as compact JSON for browser EventSource or fetch readers.
    payload = json.dumps(data, ensure_ascii=False)
    # Return a complete SSE frame.
    return f"event: {event}\ndata: {payload}\n\n"


# Stream LLM tokens as SSE frames.
async def stream_llm_response(messages: list[dict[str, str]], max_tokens: int, model_name: str | None = None, start_data: dict[str, Any] | None = None) -> AsyncIterator[str]:
    # Build the first event payload with optional routing metadata.
    first_event_data = {"status": "streaming"}
    # Merge routing metadata into the start event when provided.
    if start_data:
        # Update the start event with model names or difficulty labels.
        first_event_data.update(start_data)
    # Send a first event immediately so clients can confirm the stream opened.
    yield sse_event("start", first_event_data)
    # Convert LLM errors into SSE error events.
    try:
        # Stream provider tokens through the singleton LLM connector.
        async for token in get_llm_connector().stream_messages(messages=messages, temperature=0.2, max_tokens=max_tokens, model_name=model_name):
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
