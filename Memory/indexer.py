from __future__ import annotations

import concurrent.futures
from typing import Optional

from Memory.chroma_factory import DEFAULT_PERSIST_DIRECTORY, delete_collection, get_or_create_collection
from Memory.embeddings import _BATCH_SIZE


COLLECTION_NAME = "code_chunks"
# Max parallel embedding requests — keeps OpenRouter rate limits comfortable.
_MAX_EMBED_WORKERS = 4


def build_document_text(chunk: dict) -> str:
    return (
        f"File path: {chunk['file_path']}\n"
        f"Type: {chunk['type']}\n"
        f"Name: {chunk['name']}\n"
        f"Scope: {chunk['scope']}\n"
        "Code:\n"
        f"{chunk['content']}"
    )


def _embed_parallel(embed_fn, documents: list[str]) -> list[list[float]]:
    """Split documents into batches and embed them in parallel threads."""
    if not documents:
        return []
    batches = [documents[i:i + _BATCH_SIZE] for i in range(0, len(documents), _BATCH_SIZE)]
    if len(batches) == 1:
        return embed_fn._embed_batch(batches[0])
    workers = min(_MAX_EMBED_WORKERS, len(batches))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        batch_results = list(pool.map(embed_fn._embed_batch, batches))
    return [emb for batch in batch_results for emb in batch]


def index_code_chunks(chunks: list[dict], persist_directory: str = DEFAULT_PERSIST_DIRECTORY, index_signature: Optional[str] = None) -> None:
    if not isinstance(chunks, list):
        raise ValueError("chunks must be a list.")
    if len(chunks) == 0:
        raise ValueError("chunks cannot be empty.")

    delete_collection(collection_name=COLLECTION_NAME, persist_directory=persist_directory)

    collection = get_or_create_collection(
        collection_name=COLLECTION_NAME,
        persist_directory=persist_directory,
        metadata={
            "chunks_signature": index_signature or "",
            "chunk_count": len(chunks),
        },
    )

    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        ids.append(chunk["chunk_id"])
        documents.append(build_document_text(chunk))
        metadatas.append(
            {
                "chunk_id": chunk["chunk_id"],
                "file_path": chunk["file_path"],
                "type": chunk["type"],
                "name": chunk["name"],
                "scope": chunk["scope"],
                "content": chunk["content"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
            }
        )

    # Pre-compute embeddings in parallel so upsert() stores them directly
    # without making a second API call.
    embed_fn = collection._embedding_function
    embeddings = _embed_parallel(embed_fn, documents)

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def get_indexed_chunks_count(persist_directory: str = DEFAULT_PERSIST_DIRECTORY) -> int:
    collection = get_or_create_collection(
        collection_name=COLLECTION_NAME,
        persist_directory=persist_directory,
    )
    return collection.count()
