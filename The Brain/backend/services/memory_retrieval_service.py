"""This file owns lightweight relevant-context retrieval for the Dockerized app flow."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import logging so retrieval source is visible in Docker logs.
import logging
# Import re so query and code text can be tokenized.
import re
# Import Any so chunk dictionaries can be typed flexibly.
from typing import Any

# Import Chroma readiness checks so retrieval never blocks on a cold vector store.
from backend.services.chroma_index_service import is_chroma_ready_for_chunks
# Import chunk normalization so old and tree-sitter chunk shapes both work.
from Memory.chunk_adapter import normalize_chunk

# Create a logger for retrieval diagnostics.
logger = logging.getLogger(__name__)

# Define query words that should not create lexical relevance by themselves.
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "if",
    "in",
    "instead",
    "is",
    "it",
    "me",
    "my",
    "normal",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "there",
    "this",
    "to",
    "u",
    "use",
    "want",
    "what",
    "when",
    "where",
    "why",
    "with",
}


# Retrieve relevant code snippets from ChromaDB when available, falling back to in-request chunks.
def retrieve_relevant_context(query: str, code_chunks_json: list[dict[str, Any]], selected_file_path: str | None = None, top_k: int | None = None) -> list[dict[str, Any]]:
    # Return only context for callers that do not need retrieval metadata.
    return retrieve_relevant_context_with_metadata(query, code_chunks_json, selected_file_path, top_k)["relevant_context"]


# Retrieve relevant code snippets and include source metadata for logs/API responses.
def retrieve_relevant_context_with_metadata(query: str, code_chunks_json: list[dict[str, Any]], selected_file_path: str | None = None, top_k: int | None = None) -> dict[str, Any]:
    # Reject empty queries because retrieval needs text.
    if not query.strip():
        # Log and return no context for empty prompts.
        log_retrieval_decision(query, "none", selected_file_path, 0, 0, 0, top_k, "empty_query")
        return {"relevant_context": [], "retrieval_source": "none", "chroma_results": 0, "fallback_results": 0}
    # Query the Chroma-backed Memory index first.
    chroma_context = retrieve_chroma_context(query, code_chunks_json, top_k)
    # Selected graph files need a deterministic boost from the in-request chunks.
    if selected_file_path:
        # Retrieve selected-file lexical matches.
        lexical_context = retrieve_lexical_context(query, code_chunks_json, selected_file_path, top_k)
        # Merge selected-file lexical matches with Chroma results.
        merged_context = merge_contexts(lexical_context, chroma_context, top_k)
        # Report mixed context when both sources contributed.
        retrieval_source = "mixed" if chroma_context else "fallback"
        # Log the exact source decision.
        log_retrieval_decision(query, retrieval_source, selected_file_path, len(chroma_context), len(lexical_context), len(merged_context), top_k, "selected_file")
        # Return context and metadata.
        return {"relevant_context": merged_context, "retrieval_source": retrieval_source, "chroma_results": len(chroma_context), "fallback_results": len(lexical_context)}
    # Prefer Chroma results when the repo has been indexed.
    if chroma_context:
        # Return Chroma-filtered snippets.
        log_retrieval_decision(query, "chroma", selected_file_path, len(chroma_context), 0, len(chroma_context), top_k, "chroma_ready")
        return {"relevant_context": chroma_context, "retrieval_source": "chroma", "chroma_results": len(chroma_context), "fallback_results": 0}
    # Fall back to lexical retrieval when Chroma has no indexed collection/results.
    lexical_context = retrieve_lexical_context(query, code_chunks_json, selected_file_path, top_k)
    # Log the fallback source decision.
    log_retrieval_decision(query, "fallback", selected_file_path, 0, len(lexical_context), len(lexical_context), top_k, "chroma_unavailable_or_empty")
    # Return lexical fallback context and metadata.
    return {"relevant_context": lexical_context, "retrieval_source": "fallback", "chroma_results": 0, "fallback_results": len(lexical_context)}


# Retrieve snippets from the persistent ChromaDB Memory collection.
def retrieve_chroma_context(query: str, code_chunks_json: list[dict[str, Any]], top_k: int | None) -> list[dict[str, Any]]:
    # Skip Chroma until the persistent collection is known to match this repo's chunks.
    if not is_chroma_ready_for_chunks(code_chunks_json):
        return []
    # Import lazily so local tools without ChromaDB can still parse this module.
    try:
        from Memory.retriever import retrieve_snippets
    except Exception:
        return []
    # Query the persistent Memory collection.
    try:
        snippets = retrieve_snippets(query)
    except Exception:
        return []
    # Apply an explicit caller limit only when one was provided.
    selected_snippets = snippets[:top_k] if top_k is not None else snippets
    # Normalize Memory snippet keys into Brain relevant_context keys.
    return [to_relevant_context(snippet, float(snippet.get("score") or 0.0)) for snippet in selected_snippets]


# Retrieve relevant code snippets from provided code_chunks_json without an external vector store.
def retrieve_lexical_context(query: str, code_chunks_json: list[dict[str, Any]], selected_file_path: str | None = None, top_k: int | None = None) -> list[dict[str, Any]]:
    # Tokenize the user query once.
    query_tokens = tokenize(query)
    # Score every chunk.
    scored_chunks = []
    # Iterate over code chunks.
    for index, chunk in enumerate(code_chunks_json, start=1):
        # Normalize old and new chunk shapes before scoring.
        normalized_chunk = normalize_chunk(chunk, index)
        if normalized_chunk is None:
            continue
        # Score the chunk against the query.
        score = score_chunk(normalized_chunk, query_tokens, selected_file_path)
        # Keep chunks with positive relevance.
        if score > 0:
            # Store score and chunk.
            scored_chunks.append((score, normalized_chunk))
    # Sort by descending relevance.
    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    # Keep every relevant chunk unless the caller explicitly provides a limit.
    selected_chunks = scored_chunks[:top_k] if top_k is not None else scored_chunks
    # Convert selected chunks into Brain-compatible relevant_context objects.
    return [to_relevant_context(chunk, score) for score, chunk in selected_chunks]


# Merge context lists without duplicating the same file/function/content tuple.
def merge_contexts(primary_context: list[dict[str, Any]], secondary_context: list[dict[str, Any]], top_k: int | None) -> list[dict[str, Any]]:
    # Prepare a stable merged list.
    merged_context = []
    # Track context identity values already added.
    seen_keys = set()
    # Add primary context first so selected-file lexical matches keep priority.
    for snippet in [*primary_context, *secondary_context]:
        # Build a dedupe key from stable source fields.
        dedupe_key = (snippet.get("file_path") or "", snippet.get("function_name") or "", snippet.get("content") or "")
        # Skip duplicates.
        if dedupe_key in seen_keys:
            continue
        # Track and add the snippet.
        seen_keys.add(dedupe_key)
        merged_context.append(snippet)
    # Apply an explicit caller limit only when one was provided.
    return merged_context[:top_k] if top_k is not None else merged_context


# Score one chunk using simple lexical overlap and selected-file boosting.
def score_chunk(chunk: dict[str, Any], query_tokens: set[str], selected_file_path: str | None) -> float:
    # Empty or generic-only queries cannot create lexical relevance.
    if not query_tokens:
        if selected_file_path and selected_file_path == (chunk.get("file_path") or chunk.get("path")):
            return 0.95
        return 0.0
    # Build searchable text from common chunk fields.
    searchable_text = " ".join(str(chunk.get(key, "")) for key in ("file_path", "path", "name", "function_name", "entity_name", "scope", "type", "content"))
    # Tokenize the chunk text.
    chunk_tokens = tokenize(searchable_text)
    # Count query overlap.
    overlap = len(query_tokens & chunk_tokens)
    # Normalize lexical scores into the same 0-1 range used by Chroma scores.
    score = overlap / len(query_tokens)
    # Boost chunks from the selected graph file.
    if selected_file_path and selected_file_path == (chunk.get("file_path") or chunk.get("path")):
        # Selected files are explicitly relevant even when the prompt uses generic wording.
        score = max(score, 0.95)
    # Boost exact symbol mentions in the user query.
    name = str(chunk.get("name") or chunk.get("function_name") or chunk.get("entity_name") or "").lower()
    # Add exact name boost when the symbol appears in the query tokens.
    if name and name.lower() in query_tokens:
        # Exact symbol matches should cross the specific-code threshold.
        score = max(score, 0.9)
    # Return the final lexical score.
    return min(score, 1.0)


# Convert arbitrary text to searchable lowercase tokens.
def tokenize(value: str) -> set[str]:
    # Return alphanumeric/code identifier tokens.
    return {token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", value.lower()) if len(token) > 1 and token not in STOP_WORDS}


# Log one concise retrieval decision for Docker diagnostics.
def log_retrieval_decision(query: str, retrieval_source: str, selected_file_path: str | None, chroma_results: int, fallback_results: int, returned_results: int, top_k: int | None, reason: str) -> None:
    # Keep user prompts short in logs while preserving enough context to match requests.
    query_preview = query.strip().replace("\n", " ")[:120]
    # Emit a stable key-value log line for grep.
    logger.info(
        "memory_retrieval retrieval_source=%s reason=%s chroma_results=%s fallback_results=%s returned_results=%s selected_file=%s top_k=%s query=%r",
        retrieval_source,
        reason,
        chroma_results,
        fallback_results,
        returned_results,
        selected_file_path or "none",
        top_k if top_k is not None else "none",
        query_preview,
    )


# Convert a scored chunk into the relevant_context shape consumed by Brain.
def to_relevant_context(chunk: dict[str, Any], score: float) -> dict[str, Any]:
    # Normalize possible raw chunk shapes before building relevant_context.
    normalized_chunk = normalize_chunk(chunk) or chunk
    # Return normalized context keys.
    return {
        "file_path": normalized_chunk.get("file_path") or normalized_chunk.get("path") or "",
        "function_name": normalized_chunk.get("function_name") or normalized_chunk.get("name") or normalized_chunk.get("entity_name") or "",
        "content": normalized_chunk.get("content") or normalized_chunk.get("code") or "",
        "score": round(score, 4),
        "start_line": normalized_chunk.get("start_line"),
        "end_line": normalized_chunk.get("end_line"),
    }
