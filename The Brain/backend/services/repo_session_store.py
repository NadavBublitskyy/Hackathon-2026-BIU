"""Persist ingested repository artifacts under the local data directory."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any


DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "repo_sessions"


def save_repo_session(
    github_url: str,
    structure_json: dict[str, Any],
    code_chunks_json: list[dict[str, Any]],
    graph_data: dict[str, Any],
    repo_identity: dict[str, Any] | None = None,
) -> str:
    session_id = build_session_id(github_url)
    session_dir = session_path(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    write_json(session_dir / "structure.json", structure_json)
    write_json(session_dir / "code_chunks.json", code_chunks_json)
    write_json(session_dir / "graph_data.json", graph_data)
    write_json(session_dir / "repo_identity.json", repo_identity or {})
    write_json(session_dir / "metadata.json", {"repo_session_id": session_id, "github_url": github_url})

    return session_id


def load_repo_session(repo_session_id: str) -> dict[str, Any]:
    session_dir = require_session_path(repo_session_id)
    return {
        "metadata": read_json(session_dir / "metadata.json"),
        "structure_json": read_json(session_dir / "structure.json"),
        "code_chunks_json": read_json(session_dir / "code_chunks.json"),
        "graph_data": read_json(session_dir / "graph_data.json"),
        "repo_identity": load_repo_identity(repo_session_id),
    }


def load_structure_json(repo_session_id: str) -> dict[str, Any]:
    return read_json(require_session_path(repo_session_id) / "structure.json")


def load_code_chunks_json(repo_session_id: str) -> list[dict[str, Any]]:
    chunks = read_json(require_session_path(repo_session_id) / "code_chunks.json")
    return chunks if isinstance(chunks, list) else []


def load_graph_data(repo_session_id: str) -> dict[str, Any]:
    graph = read_json(require_session_path(repo_session_id) / "graph_data.json")
    return graph if isinstance(graph, dict) else {"nodes": [], "edges": []}


def load_repo_identity(repo_session_id: str) -> dict[str, Any]:
    path = require_session_path(repo_session_id) / "repo_identity.json"
    if not path.exists():
        return {}
    identity = read_json(path)
    return identity if isinstance(identity, dict) else {}


def build_session_id(github_url: str) -> str:
    safe_hint = re.sub(r"[^A-Za-z0-9_-]+", "-", github_url.rstrip("/").split("/")[-1] or "repo").strip("-").lower()
    return f"{safe_hint or 'repo'}-{uuid.uuid4().hex[:12]}"


def require_session_path(repo_session_id: str) -> Path:
    session_dir = session_path(repo_session_id)
    if not session_dir.exists() or not session_dir.is_dir():
        raise FileNotFoundError(f"Repository session not found: {repo_session_id}")
    return session_dir


def session_path(repo_session_id: str) -> Path:
    cleaned = sanitize_session_id(repo_session_id)
    if not cleaned:
        raise ValueError("repo_session_id must be a non-empty string")
    return DATA_ROOT / cleaned


def sanitize_session_id(repo_session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "", str(repo_session_id or ""))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
