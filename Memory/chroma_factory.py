from __future__ import annotations

import os
from threading import Lock

import chromadb

from Memory.embeddings import OpenRouterEmbeddingFunction


# Anchor the DB path to this file's directory so it resolves identically
# regardless of the working directory (local run vs. Docker /app).
DEFAULT_PERSIST_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
_DEFAULT_PERSIST_DIRECTORY = DEFAULT_PERSIST_DIRECTORY
_DEFAULT_COLLECTION_NAME = "code_chunks"

_client: chromadb.PersistentClient | None = None
_embed_fn: OpenRouterEmbeddingFunction | None = None
_lock = Lock()


def _get_embed_fn() -> OpenRouterEmbeddingFunction:
    global _embed_fn
    if _embed_fn is None:
        with _lock:
            if _embed_fn is None:
                _embed_fn = OpenRouterEmbeddingFunction()
    return _embed_fn


def _get_client(persist_directory: str) -> chromadb.PersistentClient:
    global _client
    normalized = os.path.abspath(persist_directory)
    if normalized == _DEFAULT_PERSIST_DIRECTORY:
        if _client is None:
            with _lock:
                if _client is None:
                    _client = chromadb.PersistentClient(path=normalized)
        return _client
    return chromadb.PersistentClient(path=normalized)


def reset_client() -> None:
    """Clear the cached client — call this after wiping chroma_db from disk."""
    global _client
    with _lock:
        _client = None


def get_or_create_collection(
    collection_name: str = _DEFAULT_COLLECTION_NAME,
    persist_directory: str = _DEFAULT_PERSIST_DIRECTORY,
    metadata: dict | None = None,
) -> chromadb.Collection:
    kwargs: dict = {"name": collection_name, "embedding_function": _get_embed_fn()}
    if metadata is not None:
        kwargs["metadata"] = metadata
    return _get_client(persist_directory).get_or_create_collection(**kwargs)


def get_collection(
    collection_name: str = _DEFAULT_COLLECTION_NAME,
    persist_directory: str = _DEFAULT_PERSIST_DIRECTORY,
) -> chromadb.Collection:
    return _get_client(persist_directory).get_collection(
        name=collection_name,
        embedding_function=_get_embed_fn(),
    )


def get_embed_fn() -> OpenRouterEmbeddingFunction:
    return _get_embed_fn()


def delete_collection(
    collection_name: str = _DEFAULT_COLLECTION_NAME,
    persist_directory: str = _DEFAULT_PERSIST_DIRECTORY,
) -> None:
    try:
        _get_client(persist_directory).delete_collection(name=collection_name)
    except Exception as error:
        if error.__class__.__name__ not in {"InvalidCollectionException", "NotFoundError"}:
            raise
