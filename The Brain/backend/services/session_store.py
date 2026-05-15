"""In-memory store for the most recently ingested repo's code chunks."""

from __future__ import annotations

from typing import Any

_cached_chunks: list[dict[str, Any]] = []


def set_cached_chunks(chunks: list[dict[str, Any]]) -> None:
    global _cached_chunks
    _cached_chunks = chunks


def get_cached_chunks() -> list[dict[str, Any]]:
    return _cached_chunks
