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
    # Always return 200 so the Docker healthcheck passes regardless of key validity.
    # Callers inspect the "status" field to determine actual readiness.
    if not state.ready:
        return {
            "status": "error",
            "provider": state.provider,
            "model": state.model,
            "error": state.error,
        }
    return {"status": "ready", "provider": state.provider, "model": state.model}
