"""This file exposes repository ingestion and lightweight memory retrieval endpoints."""

# Import Any so JSON response payloads can be typed.
import asyncio
from typing import Any

# Import FastAPI tools for route registration and controlled HTTP errors.
from fastapi import APIRouter, HTTPException

# Import request schemas for repo ingestion and memory retrieval.
from backend.schemas import IngestRequest, MemoryRetrieveRequest
# Import the Chroma index coordinator.
from backend.services.chroma_index_service import get_chroma_index_status, schedule_chroma_indexing
# Import the public GitHub ingestor service.
from backend.services.repo_ingest_service import ingest_public_repo
# Import the lightweight retrieval service.
from backend.services.memory_retrieval_service import retrieve_relevant_context_with_metadata
# Import the backend chunk cache so chunks are stored once after ingest.
from backend.services.session_store import set_cached_chunks

# Create the router mounted by main.py.
router = APIRouter()


# Register the endpoint that creates structure.json, code_chunks.json, and graph data.
@router.post("/api/ingest")
async def ingest_repo(request: IngestRequest) -> dict[str, Any]:
    # Convert ingestion validation errors into clear HTTP 400 responses.
    try:
        # Ingest the public repository without a GitHub token.
        result = await ingest_public_repo(request.github_url, on_code_chunks_ready=schedule_chroma_indexing)
        # Cache chunks on the backend so queries never need to re-send them.
        set_cached_chunks(result.get("code_chunks_json", []))
        # Return structure/chunks/graph immediately; retrieval can use lexical fallback until Chroma is ready.
        return result
    # Convert expected user-facing failures into bad request responses.
    except ValueError as exc:
        # Return a clear validation error.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# Register the endpoint that retrieves relevant snippets from code_chunks_json.
@router.post("/api/memory/retrieve")
async def retrieve_memory(request: MemoryRetrieveRequest) -> dict[str, Any]:
    # Choose the primary user query field.
    query = request.user_query or request.prompt or ""
    # Run the sync retrieval (blocking embedding HTTP call) on a thread so the event loop stays free.
    retrieval_result = await asyncio.to_thread(
        retrieve_relevant_context_with_metadata, query, request.code_chunks_json, request.selected_file_path, request.top_k
    )
    # Return the shape expected by the frontend and Brain flow.
    return {**retrieval_result, "memory_status": get_chroma_index_status(request.code_chunks_json)}
