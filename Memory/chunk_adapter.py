"""Normalize code chunk shapes used by ingestion, retrieval, and indexing."""

from __future__ import annotations

import hashlib
from typing import Any


def normalize_chunk(chunk: dict[str, Any], index: int | None = None) -> dict[str, Any] | None:
    """Return the canonical chunk shape, accepting old and tree-sitter chunk formats."""

    if not isinstance(chunk, dict):
        return None

    file_path = first_text(chunk, ("file_path", "path", "filename", "file"))
    content = first_text(chunk, ("content", "code", "text"))

    if not file_path or not content:
        return None

    start_line, end_line = read_line_range(chunk)
    name = first_text(chunk, ("name", "function_name", "entity_name", "symbol")) or "Unnamed"
    chunk_type = normalize_type(first_text(chunk, ("type", "kind", "node_type")))
    scope = first_text(chunk, ("scope", "parent", "container")) or "global"
    chunk_id = first_text(chunk, ("chunk_id", "id")) or build_chunk_id(file_path, chunk_type, name, start_line, end_line, content, index)

    return {
        "chunk_id": chunk_id,
        "file_path": file_path,
        "type": chunk_type,
        "name": name,
        "scope": scope,
        "content": content,
        "start_line": start_line,
        "end_line": end_line,
    }


def normalize_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a list of chunks and drop invalid entries."""

    if not isinstance(chunks, list):
        return []

    normalized_chunks = []

    for index, chunk in enumerate(chunks, start=1):
        normalized_chunk = normalize_chunk(chunk, index)
        if normalized_chunk is not None:
            normalized_chunks.append(normalized_chunk)

    return normalized_chunks


def first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Return the first non-empty string-like value for the given keys."""

    for key in keys:
        value = data.get(key)
        if value is None:
            continue

        text = str(value).strip()
        if text:
            return text

    return ""


def read_line_range(chunk: dict[str, Any]) -> tuple[int, int]:
    """Read start/end line values from old or new chunk formats."""

    line_range = chunk.get("line_range")
    if isinstance(line_range, (list, tuple)) and len(line_range) >= 2:
        start_line = parse_positive_int(line_range[0], 1)
        end_line = parse_positive_int(line_range[1], start_line)
        return start_line, max(start_line, end_line)

    if isinstance(line_range, dict):
        start_line = parse_positive_int(line_range.get("start") or line_range.get("start_line"), 1)
        end_line = parse_positive_int(line_range.get("end") or line_range.get("end_line"), start_line)
        return start_line, max(start_line, end_line)

    start_line = parse_positive_int(chunk.get("start_line") or chunk.get("start"), 1)
    end_line = parse_positive_int(chunk.get("end_line") or chunk.get("end"), start_line)

    return start_line, max(start_line, end_line)


def parse_positive_int(value: Any, fallback: int) -> int:
    """Parse a positive integer line number with a safe fallback."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback

    return parsed if parsed > 0 else fallback


def normalize_type(value: str) -> str:
    """Normalize chunk type labels from different chunkers."""

    normalized = value.strip().lower()
    if normalized == "class":
        return "class"
    if normalized in {"function", "method", "constructor"}:
        return "function"
    if normalized:
        return normalized
    return "chunk"


def build_chunk_id(file_path: str, chunk_type: str, name: str, start_line: int, end_line: int, content: str, index: int | None) -> str:
    """Build a stable chunk id when the chunker did not provide one."""

    if index is not None:
        return f"ch_{index}"

    digest = hashlib.sha1(f"{file_path}\0{chunk_type}\0{name}\0{start_line}\0{end_line}\0{content}".encode("utf-8", errors="replace")).hexdigest()
    return f"ch_{digest[:12]}"
