"""This file owns lightweight relevant-context retrieval for the Dockerized app flow."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import re so query and code text can be tokenized.
import re
# Import Any so chunk dictionaries can be typed flexibly.
from typing import Any


# Retrieve relevant code snippets from code_chunks_json without an external vector store.
def retrieve_relevant_context(query: str, code_chunks_json: list[dict[str, Any]], selected_file_path: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
    # Reject empty queries because retrieval needs text.
    if not query.strip():
        # Return no context for empty prompts.
        return []
    # Tokenize the user query once.
    query_tokens = tokenize(query)
    # Score every chunk.
    scored_chunks = []
    # Iterate over code chunks.
    for chunk in code_chunks_json:
        # Score the chunk against the query.
        score = score_chunk(chunk, query_tokens, selected_file_path)
        # Keep chunks with positive relevance.
        if score > 0:
            # Store score and chunk.
            scored_chunks.append((score, chunk))
    # Sort by descending relevance.
    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    # Convert top chunks into Brain-compatible relevant_context objects.
    return [to_relevant_context(chunk, score) for score, chunk in scored_chunks[:top_k]]


# Score one chunk using simple lexical overlap and selected-file boosting.
def score_chunk(chunk: dict[str, Any], query_tokens: set[str], selected_file_path: str | None) -> float:
    # Build searchable text from common chunk fields.
    searchable_text = " ".join(str(chunk.get(key, "")) for key in ("file_path", "path", "name", "function_name", "scope", "type", "content"))
    # Tokenize the chunk text.
    chunk_tokens = tokenize(searchable_text)
    # Count query overlap.
    overlap = len(query_tokens & chunk_tokens)
    # Start the score from overlap size.
    score = float(overlap)
    # Boost chunks from the selected graph file.
    if selected_file_path and selected_file_path == (chunk.get("file_path") or chunk.get("path")):
        # Add a strong selected-file boost.
        score += 6.0
    # Boost exact symbol mentions in the user query.
    name = str(chunk.get("name") or chunk.get("function_name") or "").lower()
    # Add exact name boost when the symbol appears in the query tokens.
    if name and name.lower() in query_tokens:
        # Add symbol boost.
        score += 4.0
    # Return the final lexical score.
    return score


# Convert arbitrary text to searchable lowercase tokens.
def tokenize(value: str) -> set[str]:
    # Return alphanumeric/code identifier tokens.
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", value.lower()))


# Convert a scored chunk into the relevant_context shape consumed by Brain.
def to_relevant_context(chunk: dict[str, Any], score: float) -> dict[str, Any]:
    # Return normalized context keys.
    return {
        "file_path": chunk.get("file_path") or chunk.get("path") or "",
        "function_name": chunk.get("function_name") or chunk.get("name") or "",
        "content": chunk.get("content") or chunk.get("code") or "",
        "score": round(score, 4),
        "start_line": chunk.get("start_line"),
        "end_line": chunk.get("end_line"),
    }
