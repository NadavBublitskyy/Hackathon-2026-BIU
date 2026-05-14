"""This file exposes The Brain service as a FastAPI API."""

# Import logging so route failures can be written to the backend logs.
import logging
# Import asynccontextmanager so FastAPI can run setup and cleanup code.
from contextlib import asynccontextmanager
# Import Any so route responses can contain flexible JSON-compatible values.
from typing import Any

# Import Body for raw request bodies, FastAPI to create the API app, and HTTPException for controlled errors.
from fastapi import Body, FastAPI, HTTPException
# Import CORS middleware so the frontend can call this backend from the browser.
from fastapi.middleware.cors import CORSMiddleware
# Import Pydantic tools so request bodies can be validated.
from pydantic import BaseModel, Field

# Import blueprint prompt templates for the /api/blueprint endpoint.
from backend.llm_blueprint import LLM_BLUEPRINT_HUMAN_PROMPT, LLM_BLUEPRINT_SYSTEM_PROMPT
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


# Register the implementation blueprint endpoint.
@app.post("/api/blueprint")
# Use the blueprint prompt wrapper to generate a file-by-file implementation plan from raw prompt text.
async def blueprint(prompt: str = Body(..., media_type="text/plain", min_length=1)) -> dict[str, Any]:
    # Convert LLM errors into clear HTTP responses.
    try:
        # Send the raw prompt through the blueprint system instructions with hardcoded LLM settings.
        result = await get_llm_connector().send_message_to_llm_wrapped_by(system_prompt=LLM_BLUEPRINT_SYSTEM_PROMPT, human_prompt_template=LLM_BLUEPRINT_HUMAN_PROMPT, values={"current_prompt": prompt, "cycle_feedback": "None"}, temperature=0.2, max_tokens=1200)
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
    # Return only the generated blueprint text.
    return {"blueprint": result.message}
