"""This file exposes readiness/status endpoints for the Brain backend."""

# Import Any so response payloads can include simple provider metadata.
from typing import Any

# Import FastAPI tools for route registration and controlled HTTP errors.
from fastapi import APIRouter, HTTPException

# Import the singleton status helper from the LLM client module.
from backend.llm_client import get_llm_status

# Create the router mounted by main.py.
router = APIRouter()


# Register the endpoint that reports whether the LLM client is ready.
@router.get("/api/llm/status")
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
