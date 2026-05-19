from typing import Any

from fastapi import APIRouter, Body, HTTPException

from Graph.graph_builder import build_graph, get_node_details


router = APIRouter(prefix="/graph", tags=["Graph"])


@router.post("")
def generate_graph(structure: dict) -> dict:
    return build_graph(structure)


@router.post("/node-details")
def generate_node_details(request_body: Any = Body(None)) -> dict:
    if not isinstance(request_body, dict):
        raise HTTPException(status_code=400, detail="request body must be a dictionary")

    structure = request_body.get("structure")
    repo_session_id = request_body.get("repo_session_id")
    node_id = request_body.get("node_id")

    if repo_session_id:
        try:
            from backend.services.repo_session_store import load_structure_json

            structure = load_structure_json(repo_session_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not isinstance(structure, dict):
        raise HTTPException(status_code=400, detail="structure must be a dictionary")

    if not isinstance(node_id, str) or not node_id.strip():
        raise HTTPException(status_code=400, detail="node_id must be a non-empty string")

    details = get_node_details(structure, node_id)
    if details is None:
        raise HTTPException(status_code=404, detail="node not found")

    return details
