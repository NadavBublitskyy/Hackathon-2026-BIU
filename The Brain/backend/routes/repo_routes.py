"""This file exposes repository ingestion and lightweight memory retrieval endpoints."""

# Import Any so JSON response payloads can be typed.
from typing import Any

# Import FastAPI tools for route registration, background work, and controlled HTTP errors.
from fastapi import APIRouter, BackgroundTasks, HTTPException

# Import request schemas for repo ingestion and memory retrieval.
from backend.schemas import IngestRequest, MemoryRetrieveRequest
# Import the Chroma index coordinator.
from backend.services.chroma_index_service import get_chroma_index_status, schedule_chroma_indexing
# Import the public GitHub ingestor service.
from backend.services.repo_ingest_service import ingest_public_repo
# Import the lightweight retrieval service.
from backend.services.memory_retrieval_service import retrieve_relevant_context_with_metadata
# Import persisted repo-session helpers.
from backend.services.repo_session_store import load_code_chunks_json, load_structure_json, save_repo_session

# Create the router mounted by main.py.
router = APIRouter()


# Register the endpoint that creates structure.json, code_chunks.json, and graph data.
@router.post("/api/ingest")
async def ingest_repo(request: IngestRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    # Convert ingestion validation errors into clear HTTP 400 responses.
    try:
        # Ingest the public repository without a GitHub token.
        result = await ingest_public_repo(request.github_url)
        repo_session_id = save_repo_session(request.github_url, result["structure_json"], result["code_chunks_json"], result["graph_data"], result["repo_identity"])
        background_tasks.add_task(schedule_chroma_indexing_after_response, result["code_chunks_json"])
        return {
            "repo_session_id": repo_session_id,
            "graph_data": result["graph_data"],
            "indexing_scheduled": True,
        }
    # Convert expected user-facing failures into bad request responses.
    except ValueError as exc:
        # Return a clear validation error.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# Register the endpoint that retrieves relevant snippets from code_chunks_json.
@router.post("/api/memory/retrieve")
async def retrieve_memory(request: MemoryRetrieveRequest) -> dict[str, Any]:
    # Choose the primary user query field.
    query = request.user_query or request.prompt or ""
    code_chunks_json = request.code_chunks_json
    structure_json = request.structure_json

    if request.repo_session_id:
        try:
            code_chunks_json = load_code_chunks_json(request.repo_session_id)
            structure_json = load_structure_json(request.repo_session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Retrieve relevant context from the provided chunks.
    retrieval_result = retrieve_relevant_context_with_metadata(
        query,
        code_chunks_json,
        request.selected_file_path,
        request.top_k,
        structure_json,
        request.context_scope,
    )
    # Return the shape expected by the frontend and Brain flow.
    return {**retrieval_result, "memory_status": get_chroma_index_status(code_chunks_json)}


async def schedule_chroma_indexing_after_response(code_chunks_json: list[dict[str, Any]]) -> None:
    schedule_chroma_indexing(code_chunks_json)
