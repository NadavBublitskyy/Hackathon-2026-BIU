"""Coordinate ChromaDB Memory indexing without blocking chat requests."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from Memory.chunk_adapter import normalize_chunks

logger = logging.getLogger(__name__)

_pending_chunks: list[dict[str, Any]] | None = None
_pending_signature: str | None = None
_worker_task: asyncio.Task | None = None
_indexing_signature: str | None = None
_ready_signature: str | None = None
_state = "idle"
_last_error: str | None = None


def schedule_chroma_indexing(code_chunks_json: list[dict[str, Any]]) -> dict[str, Any]:
    """Queue ChromaDB indexing on a background thread and return current status."""

    global _pending_chunks, _pending_signature, _worker_task, _state, _last_error

    chunks = clone_chunks(code_chunks_json)
    signature = build_chunks_signature(chunks)

    if not chunks:
        _state = "idle"
        _pending_chunks = None
        _pending_signature = None
        return get_chroma_index_status(chunks)

    if _ready_signature == signature:
        _state = "ready"
        logger.info("chroma_index schedule=skip reason=memory_ready signature=%s chunks=%s", signature, len(chunks))
        return get_chroma_index_status(chunks)

    if persisted_collection_matches(signature, len(chunks)):
        _state = "ready"
        logger.info("chroma_index schedule=skip reason=persisted_collection_ready signature=%s chunks=%s", signature, len(chunks))
        return get_chroma_index_status(chunks)

    if _indexing_signature == signature and _pending_signature is None:
        _state = "indexing"
        logger.info("chroma_index schedule=skip reason=already_indexing signature=%s chunks=%s", signature, len(chunks))
        return get_chroma_index_status(chunks)

    if _pending_signature == signature:
        _state = "queued"
        logger.info("chroma_index schedule=skip reason=already_queued signature=%s chunks=%s", signature, len(chunks))
        return get_chroma_index_status(chunks)

    _pending_chunks = chunks
    _pending_signature = signature
    _last_error = None

    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(run_index_worker())

    _state = "queued"
    logger.info("chroma_index schedule=queued signature=%s chunks=%s", signature, len(chunks))
    return get_chroma_index_status(chunks)


def is_chroma_ready_for_chunks(code_chunks_json: list[dict[str, Any]]) -> bool:
    """Return true only when the persistent Chroma collection matches these chunks."""

    global _ready_signature, _state

    chunks = clone_chunks(code_chunks_json)
    if not chunks:
        return False

    signature = build_chunks_signature(chunks)
    if _ready_signature == signature:
        return True

    collection_state = read_persistent_collection_state()
    if (
        collection_state.get("chunks_signature") == signature
        and collection_state.get("count") == len(chunks)
    ):
        _ready_signature = signature
        _state = "ready"
        return True

    return False


def persisted_collection_matches(signature: str, chunk_count: int) -> bool:
    """Return true when the on-disk Chroma collection already contains this repo."""

    global _ready_signature

    collection_state = read_persistent_collection_state()
    if (
        collection_state.get("chunks_signature") == signature
        and collection_state.get("count") == chunk_count
    ):
        _ready_signature = signature
        return True

    return False


def get_chroma_index_status(code_chunks_json: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return lightweight Chroma indexing state for diagnostics."""

    ready_for_chunks = None
    chunks_signature = None

    if code_chunks_json is not None:
        chunks = clone_chunks(code_chunks_json)
        chunks_signature = build_chunks_signature(chunks) if chunks else None
        ready_for_chunks = is_chroma_ready_for_chunks(chunks) if chunks else False

    return {
        "state": _state,
        "pending_signature": _pending_signature,
        "indexing_signature": _indexing_signature,
        "ready_signature": _ready_signature,
        "chunks_signature": chunks_signature,
        "ready_for_chunks": ready_for_chunks,
        "last_error": _last_error,
    }


async def run_index_worker() -> None:
    """Index the newest queued chunks, serially, on a worker thread."""

    global _pending_chunks, _pending_signature, _indexing_signature, _ready_signature, _state, _last_error

    while True:
        chunks = _pending_chunks
        signature = _pending_signature
        _pending_chunks = None
        _pending_signature = None

        if not chunks or not signature:
            _state = "ready" if _ready_signature else "idle"
            return

        _state = "indexing"
        _indexing_signature = signature

        try:
            await asyncio.to_thread(index_chunks_sync, chunks, signature)
        except Exception as exc:
            _last_error = f"{exc.__class__.__name__}: {exc}"
            logger.exception("Failed to index code chunks into ChromaDB Memory.")
            if _pending_chunks is None:
                _state = "failed"
                _indexing_signature = None
                return
        else:
            _ready_signature = signature
            _last_error = None
            _state = "queued" if _pending_chunks is not None else "ready"
            _indexing_signature = None

        if _pending_chunks is None:
            return


def index_chunks_sync(chunks: list[dict[str, Any]], signature: str) -> None:
    """Run the blocking ChromaDB indexer with a repo signature."""

    from Memory.indexer import index_code_chunks

    index_code_chunks(chunks, index_signature=signature)


def read_persistent_collection_state() -> dict[str, Any]:
    """Read Chroma collection metadata without running an embedding query."""

    try:
        from Memory.retriever import get_collection_state

        return get_collection_state()
    except Exception:
        return {"exists": False, "count": 0, "chunks_signature": None}


def clone_chunks(code_chunks_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize chunks so background indexing does not share mutable input."""

    if not isinstance(code_chunks_json, list):
        return []

    return normalize_chunks([dict(chunk) for chunk in code_chunks_json if isinstance(chunk, dict)])


def build_chunks_signature(chunks: list[dict[str, Any]]) -> str:
    """Build a stable signature for a code_chunks_json payload."""

    hasher = hashlib.sha256()
    hasher.update(str(len(chunks)).encode("utf-8"))

    for chunk in chunks:
        for key in ("chunk_id", "file_path", "type", "name", "scope", "start_line", "end_line"):
            hasher.update(str(chunk.get(key, "")).encode("utf-8", errors="replace"))
            hasher.update(b"\0")

        content = str(chunk.get("content", ""))
        hasher.update(hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest().encode("ascii"))
        hasher.update(b"\0")

    return hasher.hexdigest()
