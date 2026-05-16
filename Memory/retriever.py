import chromadb


DEFAULT_PERSIST_DIRECTORY = "Memory/chroma_db"
DEFAULT_COLLECTION_NAME = "code_chunks"
_N_RESULTS_CAP = 30

_clients: dict[str, chromadb.PersistentClient] = {}


def _get_chroma_client(path: str) -> chromadb.PersistentClient:
    if path not in _clients:
        _clients[path] = chromadb.PersistentClient(path=path)
    return _clients[path]


def get_collection_state(
    collection_name: str = DEFAULT_COLLECTION_NAME,
    persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
) -> dict:
    """
    Returns collection metadata without running an embedding query.
    """

    client = _get_chroma_client(persist_directory)

    try:
        collection = client.get_collection(name=collection_name)
    except Exception as error:
        if error.__class__.__name__ in {"InvalidCollectionException", "NotFoundError"}:
            return {
                "exists": False,
                "count": 0,
                "metadata": {},
                "chunks_signature": None,
            }

        raise

    metadata = collection.metadata or {}

    return {
        "exists": True,
        "count": collection.count(),
        "metadata": metadata,
        "chunks_signature": metadata.get("chunks_signature"),
    }


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


def filter_snippets_by_relative_score(
    snippets: list[dict],
    relative_score_threshold: float,
    min_score: float,
) -> list[dict]:
    """
    Keeps snippets close enough to the best result score.
    """

    if len(snippets) == 0:
        return []

    best_score = max(snippet["score"] for snippet in snippets)
    minimum_score = best_score * relative_score_threshold

    return [
        snippet
        for snippet in snippets
        if snippet["score"] >= minimum_score and snippet["score"] >= min_score
    ]


def retrieve_snippets(
    query: str,
    relative_score_threshold: float = 0.85,
    min_score: float = 0.40,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
) -> list[dict]:
    """
    Retrieves the most relevant code snippets from an existing ChromaDB collection.
    """

    if query is None or query.strip() == "":
        raise ValueError("query cannot be empty.")

    if relative_score_threshold <= 0:
        raise ValueError("relative_score_threshold must be greater than 0.")

    if min_score < 0:
        raise ValueError("min_score cannot be negative.")

    client = _get_chroma_client(persist_directory)

    try:
        collection = client.get_collection(name=collection_name)
    except Exception as error:
        if error.__class__.__name__ in {"InvalidCollectionException", "NotFoundError"}:
            return []

        raise

    indexed_chunks_count = collection.count()

    if indexed_chunks_count == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(_N_RESULTS_CAP, indexed_chunks_count),
        include=["documents", "metadatas", "distances"],
    )

    snippets = build_snippet_results(results)

    return filter_snippets_by_relative_score(snippets, relative_score_threshold, min_score)
