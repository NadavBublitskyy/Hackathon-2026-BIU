import chromadb


DEFAULT_PERSIST_DIRECTORY = "Memory/chroma_db"
DEFAULT_COLLECTION_NAME = "code_chunks"


def distance_to_score(distance: float) -> float:
    """
    Converts a ChromaDB distance into a relevance score.
    """

    score = 1 / (1 + distance)

    return round(score, 4)


def build_snippet_results(results: dict) -> list[dict]:
    """
    Builds snippet dictionaries from ChromaDB query results.
    """

    documents_groups = results.get("documents") or []
    metadatas_groups = results.get("metadatas") or []
    distances_groups = results.get("distances") or []

    if len(documents_groups) == 0:
        return []

    documents = documents_groups[0] or []

    if len(documents) == 0:
        return []

    metadatas = metadatas_groups[0] if len(metadatas_groups) > 0 else []
    distances = distances_groups[0] if len(distances_groups) > 0 else []

    snippets = []

    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and metadatas[index] else {}
        distance = distances[index] if index < len(distances) else None
        score = distance_to_score(distance) if distance is not None else 0.0

        snippets.append(
            {
                "path": metadata.get("file_path", ""),
                "code": metadata.get("content", document),
                "score": score,
                "chunk_id": metadata.get("chunk_id", ""),
                "name": metadata.get("name", ""),
                "type": metadata.get("type", ""),
                "scope": metadata.get("scope", ""),
                "start_line": metadata.get("start_line"),
                "end_line": metadata.get("end_line"),
            }
        )

    return snippets


def retrieve_snippets(
    query: str,
    top_k: int = 5,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
) -> list[dict]:
    """
    Retrieves the most relevant code snippets from an existing ChromaDB collection.
    """

    if query is None or query.strip() == "":
        raise ValueError("query cannot be empty.")

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0.")

    client = chromadb.PersistentClient(path=persist_directory)

    try:
        collection = client.get_collection(name=collection_name)
    except Exception as error:
        if error.__class__.__name__ in {"InvalidCollectionException", "NotFoundError"}:
            return []

        raise

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    return build_snippet_results(results)
