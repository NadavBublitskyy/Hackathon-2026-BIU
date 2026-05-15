"""Repository ingestion orchestration for the FastAPI backend."""

from __future__ import annotations

from typing import Any

from Graph.graph_builder import build_graph
from Ingestor import ingest_repo


async def ingest_public_repo(github_url: str) -> dict[str, Any]:
    milestone_payload = ingest_repo(github_url)
    structure_json = milestone_payload["structure_json"]
    code_chunks_json = milestone_payload["code_chunks_json"]
    graph_data = build_graph(structure_json)

    return {
        "structure_json": structure_json,
        "code_chunks_json": code_chunks_json,
        "graph_data": graph_data,
    }
