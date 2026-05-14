import chromadb


COLLECTION_NAME = "code_chunks"


def build_document_text(chunk: dict) -> str:
    """
    Builds searchable text for a validated code chunk.
    """

    return (
        f"File path: {chunk['file_path']}\n"
        f"Type: {chunk['type']}\n"
        f"Name: {chunk['name']}\n"
        f"Scope: {chunk['scope']}\n"
        "Code:\n"
        f"{chunk['content']}"
    )


def index_code_chunks(chunks: list[dict], persist_directory: str = "Memory/chroma_db") -> None:
    """
    Indexes validated code chunks into a persistent ChromaDB collection.

    Args:
        chunks: Already-loaded and validated code chunks.
        persist_directory: Local directory for persistent ChromaDB storage.

    Raises:
        ValueError: If chunks is not a non-empty list.
    """

    if not isinstance(chunks, list):
        raise ValueError("chunks must be a list.")

    if len(chunks) == 0:
        raise ValueError("chunks cannot be empty.")

    client = chromadb.PersistentClient(path=persist_directory)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

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

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )


def get_indexed_chunks_count(persist_directory: str = "Memory/chroma_db") -> int:
    """
    Returns the number of chunks currently stored in the ChromaDB collection.
    """

    client = chromadb.PersistentClient(path=persist_directory)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    return collection.count()
