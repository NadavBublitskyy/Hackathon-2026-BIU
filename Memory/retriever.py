from Memory.chroma_factory import DEFAULT_PERSIST_DIRECTORY, get_collection, get_embed_fn


DEFAULT_COLLECTION_NAME = "code_chunks"

_MAX_QUERY_RESULTS = 5


def get_collection_state(
    collection_name: str = DEFAULT_COLLECTION_NAME,
    persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
) -> dict:
    try:
        collection = get_collection(
            collection_name=collection_name,
            persist_directory=persist_directory,
        )
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
    score = 1 / (1 + distance)
    return round(score, 4)


def build_snippet_results(results: dict) -> list[dict]:
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
    if query is None or query.strip() == "":
        raise ValueError("query cannot be empty.")

    if relative_score_threshold <= 0:
        raise ValueError("relative_score_threshold must be greater than 0.")

    if min_score < 0:
        raise ValueError("min_score cannot be negative.")

    try:
        collection = get_collection(
            collection_name=collection_name,
            persist_directory=persist_directory,
        )
    except Exception as error:
        if error.__class__.__name__ in {"InvalidCollectionException", "NotFoundError"}:
            return []
        raise

    indexed_chunks_count = collection.count()
    print(f"DEBUG: Querying collection with {indexed_chunks_count} docs", flush=True)

    if indexed_chunks_count == 0:
        return []

    # Pre-compute the query embedding ourselves so we control the shape passed
    # to ChromaDB's Rust bindings — query_embeddings must be list[list[float]].
    query_embedding = get_embed_fn().embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(_MAX_QUERY_RESULTS, indexed_chunks_count),
        include=["documents", "metadatas", "distances"],
    )

    snippets = build_snippet_results(results)

    return filter_snippets_by_relative_score(snippets, relative_score_threshold, min_score)
