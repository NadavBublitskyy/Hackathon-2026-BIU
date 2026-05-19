"""This file owns relevant-context retrieval when ChromaDB is cold or unavailable."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from backend.services.chroma_index_service import is_chroma_ready_for_chunks

logger = logging.getLogger(__name__)

CONTEXT_SCOPE_REPO_WIDE = "repo_wide"
CONTEXT_SCOPE_SPECIFIC_CODE = "specific_code"

BM25_K1 = 1.5
BM25_B = 0.75
LOW_CONFIDENCE_BM25_SCORE = 0.40

SELECTED_FILE_SCORE = 0.95
IMPORT_NEIGHBOR_SCORE = 0.70
ANCHOR_SUMMARY_SCORE = 0.90
ANCHOR_CHUNK_SCORE = 0.82
MAX_ANCHOR_FILES = 8
MAX_CHUNKS_PER_ANCHOR_FILE = 2
MAX_CHUNKS_PER_NEIGHBOR_FILE = 2

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

CODE_STOP_WORDS = {
    "abstract",
    "async",
    "await",
    "boolean",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "constructor",
    "continue",
    "def",
    "default",
    "else",
    "enum",
    "export",
    "extends",
    "false",
    "final",
    "finally",
    "for",
    "function",
    "if",
    "implements",
    "import",
    "int",
    "interface",
    "let",
    "new",
    "none",
    "null",
    "package",
    "private",
    "protected",
    "public",
    "return",
    "static",
    "super",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "var",
    "void",
    "while",
}

ALL_STOP_WORDS = STOP_WORDS | CODE_STOP_WORDS

DOC_ANCHOR_NAMES = {"readme", "contributing", "architecture", "docs", "overview"}
CONFIG_ANCHOR_NAMES = {
    ".env.example",
    "containerfile",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "gradle.properties",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "settings.gradle",
    "setup.py",
    "tsconfig.json",
    "vite.config.js",
    "vite.config.ts",
}
ENTRYPOINT_NAMES = {
    "app.java",
    "app.js",
    "app.jsx",
    "app.py",
    "app.ts",
    "app.tsx",
    "index.js",
    "index.jsx",
    "index.ts",
    "index.tsx",
    "main.java",
    "main.js",
    "main.py",
    "main.ts",
    "server.js",
    "server.ts",
}


def retrieve_relevant_context(
    query: str,
    code_chunks_json: list[dict[str, Any]],
    selected_file_path: str | None = None,
    top_k: int | None = None,
    structure_json: dict[str, Any] | None = None,
    context_scope: str | None = None,
) -> list[dict[str, Any]]:
    return retrieve_relevant_context_with_metadata(query, code_chunks_json, selected_file_path, top_k, structure_json, context_scope)["relevant_context"]


def retrieve_relevant_context_with_metadata(
    query: str,
    code_chunks_json: list[dict[str, Any]],
    selected_file_path: str | None = None,
    top_k: int | None = None,
    structure_json: dict[str, Any] | None = None,
    context_scope: str | None = None,
) -> dict[str, Any]:
    if not query.strip():
        log_retrieval_decision(query, "none", selected_file_path, context_scope, 0, 0, 0, 0, top_k, "empty_query")
        return {"relevant_context": [], "retrieval_source": "none", "chroma_results": 0, "fallback_results": 0, "anchor_results": 0}

    if selected_file_path:
        selected_context = context_for_file_paths([selected_file_path], code_chunks_json, structure_json, SELECTED_FILE_SCORE, "selected_file", None)
        log_retrieval_decision(query, "selected_file_only", selected_file_path, context_scope, 0, 0, 0, len(selected_context), top_k, "selected_file_only")
        return {
            "relevant_context": selected_context,
            "retrieval_source": "selected_file_only",
            "chroma_results": 0,
            "fallback_results": len(selected_context),
            "anchor_results": 0,
            "import_neighbor_results": 0,
        }

    chroma_context = retrieve_chroma_context(query, code_chunks_json, top_k)

    if context_scope == CONTEXT_SCOPE_REPO_WIDE:
        anchor_context = retrieve_anchor_context(structure_json, code_chunks_json)

        if chroma_context:
            merged_context = merge_contexts(chroma_context, anchor_context, top_k=top_k)
            log_retrieval_decision(query, "mixed_chroma_anchors", selected_file_path, context_scope, len(chroma_context), 0, len(anchor_context), len(merged_context), top_k, "repo_wide_chroma_ready")
            return {
                "relevant_context": merged_context,
                "retrieval_source": "mixed_chroma_anchors",
                "chroma_results": len(chroma_context),
                "fallback_results": len(anchor_context),
                "anchor_results": len(anchor_context),
            }

        bm25_context = retrieve_bm25_context(query, code_chunks_json, None, set(), top_k)
        best_bm25_score = max_context_score(bm25_context)

        if best_bm25_score < LOW_CONFIDENCE_BM25_SCORE:
            merged_context = merge_contexts(anchor_context, bm25_context, top_k=top_k)
            reason = "repo_wide_low_bm25_anchor_first"
        else:
            merged_context = merge_contexts(bm25_context, anchor_context, top_k=top_k)
            reason = "repo_wide_bm25_with_anchors"

        log_retrieval_decision(query, "anchor_bm25", selected_file_path, context_scope, 0, len(bm25_context), len(anchor_context), len(merged_context), top_k, reason)
        return {
            "relevant_context": merged_context,
            "retrieval_source": "anchor_bm25",
            "chroma_results": 0,
            "fallback_results": len(bm25_context) + len(anchor_context),
            "anchor_results": len(anchor_context),
            "best_bm25_score": best_bm25_score,
        }

    if chroma_context:
        log_retrieval_decision(query, "chroma", selected_file_path, context_scope, len(chroma_context), 0, 0, len(chroma_context), top_k, "chroma_ready")
        return {"relevant_context": chroma_context, "retrieval_source": "chroma", "chroma_results": len(chroma_context), "fallback_results": 0, "anchor_results": 0}

    bm25_context = retrieve_bm25_context(query, code_chunks_json, None, set(), top_k)
    log_retrieval_decision(query, "bm25", selected_file_path, context_scope, 0, len(bm25_context), 0, len(bm25_context), top_k, "chroma_unavailable_or_empty")
    return {"relevant_context": bm25_context, "retrieval_source": "bm25", "chroma_results": 0, "fallback_results": len(bm25_context), "anchor_results": 0}


def retrieve_chroma_context(query: str, code_chunks_json: list[dict[str, Any]], top_k: int | None) -> list[dict[str, Any]]:
    if not is_chroma_ready_for_chunks(code_chunks_json):
        return []

    try:
        from Memory.retriever import retrieve_snippets
    except Exception:
        return []

    try:
        snippets = retrieve_snippets(query)
    except Exception:
        return []

    selected_snippets = snippets[:top_k] if top_k is not None else snippets
    return [to_relevant_context(snippet, float(snippet.get("score") or 0.0)) for snippet in selected_snippets]


def retrieve_bm25_context(
    query: str,
    code_chunks_json: list[dict[str, Any]],
    selected_file_path: str | None,
    import_neighbor_file_paths: set[str],
    top_k: int | None,
) -> list[dict[str, Any]]:
    query_terms = tokenize_terms(query)
    if not query_terms:
        return []

    chunk_documents = [(chunk, weighted_chunk_terms(chunk)) for chunk in code_chunks_json if isinstance(chunk, dict)]
    if not chunk_documents:
        return []

    raw_scores = bm25_raw_scores(query_terms, [terms for _, terms in chunk_documents])
    scored_chunks: list[tuple[float, dict[str, Any]]] = []

    query_term_set = set(query_terms)
    for (chunk, _), raw_score in zip(chunk_documents, raw_scores):
        score = normalize_bm25_score(raw_score)
        file_path = chunk_file_path(chunk)

        if selected_file_path and file_path == selected_file_path:
            score = max(score, SELECTED_FILE_SCORE)
        elif file_path in import_neighbor_file_paths:
            score = max(score, IMPORT_NEIGHBOR_SCORE)

        if chunk_name(chunk).lower() in query_term_set:
            score = max(score, 0.90)

        if score > 0:
            scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    selected_chunks = scored_chunks[:top_k] if top_k is not None else scored_chunks
    return [to_relevant_context(chunk, score) for score, chunk in selected_chunks]


def calculate_query_relevance_score(query: str, code_chunks_json: list[dict[str, Any]]) -> float:
    context = retrieve_bm25_context(query, code_chunks_json, None, set(), top_k=1)
    return max_context_score(context)


def calculate_semantic_canary_match(query: str, code_chunks_json: list[dict[str, Any]]) -> dict[str, Any]:
    if not query.strip() or not is_chroma_ready_for_chunks(code_chunks_json):
        return {"score": 0.0, "file_path": None, "function_name": None}

    try:
        from Memory.retriever import retrieve_snippets
    except Exception:
        return {"score": 0.0, "file_path": None, "function_name": None}

    try:
        snippets = retrieve_snippets(query, relative_score_threshold=0.01, min_score=0.0, n_results=1)
    except Exception:
        return {"score": 0.0, "file_path": None, "function_name": None}

    if not snippets:
        return {"score": 0.0, "file_path": None, "function_name": None}

    best = snippets[0]
    return {
        "score": float(best.get("score") or 0.0),
        "file_path": best.get("path") or best.get("file_path"),
        "function_name": best.get("name") or best.get("function_name"),
    }


def bm25_raw_scores(query_terms: list[str], documents: list[list[str]]) -> list[float]:
    if not query_terms or not documents:
        return []

    document_counts = [Counter(document) for document in documents]
    document_lengths = [sum(counts.values()) for counts in document_counts]
    average_document_length = sum(document_lengths) / len(document_lengths) if document_lengths else 1.0
    document_frequency: Counter[str] = Counter()

    for counts in document_counts:
        for term in counts:
            document_frequency[term] += 1

    query_counts = Counter(query_terms)
    document_count = len(documents)
    scores: list[float] = []

    for counts, document_length in zip(document_counts, document_lengths):
        score = 0.0
        for term, query_frequency in query_counts.items():
            term_frequency = counts.get(term, 0)
            if term_frequency <= 0:
                continue

            idf = math.log(1 + (document_count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            denominator = term_frequency + BM25_K1 * (1 - BM25_B + BM25_B * document_length / max(average_document_length, 1.0))
            query_weight = 1 + 0.15 * (query_frequency - 1)
            score += idf * ((term_frequency * (BM25_K1 + 1)) / denominator) * query_weight

        scores.append(score)

    return scores


def normalize_bm25_score(raw_score: float) -> float:
    if raw_score <= 0:
        return 0.0
    return min(raw_score / (raw_score + 1.0), 1.0)


def retrieve_anchor_context(structure_json: dict[str, Any] | None, code_chunks_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = anchor_file_candidates(structure_json, code_chunks_json)
    if not candidates:
        return []

    chunks_by_path = group_chunks_by_path(code_chunks_json)
    contexts: list[dict[str, Any]] = []

    for _, anchor_kind, file_path, file_record in candidates[:MAX_ANCHOR_FILES]:
        contexts.append(structure_summary_context(file_path, file_record, ANCHOR_SUMMARY_SCORE, f"repo_wide_anchor:{anchor_kind}"))

        for chunk in chunks_by_path.get(file_path, [])[:MAX_CHUNKS_PER_ANCHOR_FILE]:
            contexts.append(to_relevant_context(chunk, ANCHOR_CHUNK_SCORE))

    return contexts


def anchor_file_candidates(structure_json: dict[str, Any] | None, code_chunks_json: list[dict[str, Any]]) -> list[tuple[int, str, str, dict[str, Any]]]:
    candidates: list[tuple[int, str, str, dict[str, Any]]] = []
    seen_paths: set[str] = set()

    for file_path, file_record in iter_structure_files(structure_json):
        priority, anchor_kind = anchor_priority(file_path, file_record)
        if priority <= 0 or file_path in seen_paths:
            continue
        seen_paths.add(file_path)
        candidates.append((priority, anchor_kind, file_path, file_record))

    if not candidates:
        for file_path in sorted({chunk_file_path(chunk) for chunk in code_chunks_json if chunk_file_path(chunk)}):
            priority, anchor_kind = anchor_priority(file_path, {})
            if priority > 0:
                candidates.append((priority, anchor_kind, file_path, {"path": file_path}))

    candidates.sort(key=lambda item: (-item[0], path_sort_key(item[2])))
    return candidates


def anchor_priority(file_path: str, file_record: dict[str, Any]) -> tuple[int, str]:
    normalized_path = file_path.lower()
    basename = PurePosixPath(normalized_path).name
    stem = PurePosixPath(normalized_path).stem
    file_type = str(file_record.get("type") or "").lower()

    if basename in ENTRYPOINT_NAMES or normalized_path.endswith("/src/main.java") or "/src/main/" in normalized_path:
        return 100, "entrypoint"
    if stem in DOC_ANCHOR_NAMES or basename.endswith(".md") or "/docs/" in normalized_path:
        return 90, "documentation"
    if basename in CONFIG_ANCHOR_NAMES or basename.startswith("vite.config") or basename.endswith(".config.js") or basename.endswith(".config.ts"):
        return 80, "configuration"
    if any(keyword in normalized_path for keyword in ("route", "router", "controller", "server", "api")) or any(keyword in file_type for keyword in ("controller", "api", "network")):
        return 70, "interface"

    return 0, ""


def context_for_file_paths(
    file_paths: list[str],
    code_chunks_json: list[dict[str, Any]],
    structure_json: dict[str, Any] | None,
    score: float,
    label: str,
    max_chunks_per_file: int | None,
) -> list[dict[str, Any]]:
    chunks_by_path = group_chunks_by_path(code_chunks_json)
    structure_by_path = {path: record for path, record in iter_structure_files(structure_json)}
    contexts: list[dict[str, Any]] = []

    for file_path in file_paths:
        chunks = chunks_by_path.get(file_path, [])
        selected_chunks = chunks[:max_chunks_per_file] if max_chunks_per_file is not None else chunks

        if selected_chunks:
            contexts.extend(to_relevant_context(chunk, score) for chunk in selected_chunks)
        elif file_path in structure_by_path:
            contexts.append(structure_summary_context(file_path, structure_by_path[file_path], score, label))

    return contexts


def import_neighbor_paths(selected_file_path: str, structure_json: dict[str, Any] | None) -> set[str]:
    structure_files = list(iter_structure_files(structure_json))
    all_file_paths = {path for path, _ in structure_files}
    neighbors: set[str] = set()

    for file_path, file_record in structure_files:
        imports = resolve_import_paths(file_record.get("imports") or [], all_file_paths)

        if file_path == selected_file_path:
            neighbors.update(imports)
        elif selected_file_path in imports:
            neighbors.add(file_path)

    neighbors.discard(selected_file_path)
    return neighbors


def resolve_import_paths(imports: Any, all_file_paths: set[str]) -> set[str]:
    resolved: set[str] = set()
    raw_imports = imports if isinstance(imports, list) else [imports]

    for raw_import in raw_imports:
        import_text = str(raw_import).strip()
        if not import_text:
            continue

        if import_text in all_file_paths:
            resolved.add(import_text)
            continue

        module_path = import_text.replace(".", "/")
        for suffix in (".py", ".js", ".jsx", ".ts", ".tsx", ".java"):
            candidate = f"{module_path}{suffix}"
            if candidate in all_file_paths:
                resolved.add(candidate)
                break

    return resolved


def iter_structure_files(structure_json: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(structure_json, dict):
        return []

    files = structure_json.get("files")

    if isinstance(files, dict):
        return [(path, {"path": path, **record}) for path, record in files.items() if isinstance(record, dict)]

    if isinstance(files, list):
        result = []
        for item in files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("file_path") or item.get("name") or "").strip()
            if path:
                result.append((path, item))
        return result

    return []


def structure_summary_context(file_path: str, file_record: dict[str, Any], score: float, label: str) -> dict[str, Any]:
    imports = file_record.get("imports") or []
    definitions = file_record.get("definitions") or {}
    chunks = file_record.get("chunks") or []
    chunk_names = [str(chunk.get("entity_name") or chunk.get("name") or "").strip() for chunk in chunks if isinstance(chunk, dict) and str(chunk.get("entity_name") or chunk.get("name") or "").strip()]

    content_lines = [
        f"Anchor reason: {label}",
        f"Path: {file_path}",
        f"Type: {file_record.get('type') or 'unknown'}",
        f"Language: {file_record.get('language') or 'unknown'}",
        f"Imports: {', '.join(str(value) for value in imports) if imports else 'none'}",
    ]

    definition_text = format_definitions(definitions)
    if definition_text:
        content_lines.append(f"Definitions: {definition_text}")

    if chunk_names:
        content_lines.append(f"Code entities: {', '.join(chunk_names)}")

    return {
        "file_path": file_path,
        "function_name": label,
        "content": "\n".join(content_lines),
        "score": round(score, 4),
        "start_line": None,
        "end_line": None,
    }


def format_definitions(definitions: Any) -> str:
    if isinstance(definitions, dict):
        parts = []
        for key in ("classes", "functions", "variables"):
            values = definitions.get(key) or []
            if values:
                parts.append(f"{key}: {', '.join(str(value) for value in values)}")
        return "; ".join(parts)

    if isinstance(definitions, list):
        return ", ".join(str(value) for value in definitions)

    return ""


def merge_contexts(*context_lists: list[dict[str, Any]], top_k: int | None) -> list[dict[str, Any]]:
    merged_context: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for context_list in context_lists:
        for snippet in context_list:
            dedupe_key = (snippet.get("file_path") or "", snippet.get("function_name") or "", snippet.get("content") or "")
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            merged_context.append(snippet)

    return merged_context[:top_k] if top_k is not None else merged_context


def weighted_chunk_terms(chunk: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    weighted_fields = (
        ("file_path", 4),
        ("path", 4),
        ("name", 5),
        ("entity_name", 5),
        ("function_name", 5),
        ("scope", 2),
        ("type", 2),
        ("content", 1),
    )

    for key, weight in weighted_fields:
        field_terms = tokenize_terms(str(chunk.get(key) or ""))
        for _ in range(weight):
            terms.extend(field_terms)

    return terms


def tokenize_terms(value: str) -> list[str]:
    terms: list[str] = []

    for raw_token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", value):
        expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw_token).replace("_", " ")
        for token in expanded.lower().split():
            if len(token) > 1 and token not in ALL_STOP_WORDS:
                terms.append(token)

    return terms


def group_chunks_by_path(code_chunks_json: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for chunk in code_chunks_json:
        file_path = chunk_file_path(chunk)
        if file_path:
            grouped.setdefault(file_path, []).append(chunk)
    return grouped


def chunk_file_path(chunk: dict[str, Any]) -> str:
    return str(chunk.get("file_path") or chunk.get("path") or "").strip()


def chunk_name(chunk: dict[str, Any]) -> str:
    return str(chunk.get("function_name") or chunk.get("name") or chunk.get("entity_name") or "").strip()


def path_sort_key(file_path: str) -> tuple[int, str]:
    return (file_path.count("/"), file_path)


def max_context_score(context: list[dict[str, Any]]) -> float:
    scores = []
    for item in context:
        try:
            scores.append(float(item.get("score")))
        except (TypeError, ValueError):
            continue
    return max(scores) if scores else 0.0


def log_retrieval_decision(
    query: str,
    retrieval_source: str,
    selected_file_path: str | None,
    context_scope: str | None,
    chroma_results: int,
    bm25_results: int,
    structural_results: int,
    returned_results: int,
    top_k: int | None,
    reason: str,
) -> None:
    query_preview = query.strip().replace("\n", " ")[:120]
    logger.info(
        "memory_retrieval retrieval_source=%s reason=%s chroma_results=%s bm25_results=%s structural_results=%s returned_results=%s selected_file=%s context_scope=%s top_k=%s query=%r",
        retrieval_source,
        reason,
        chroma_results,
        bm25_results,
        structural_results,
        returned_results,
        selected_file_path or "none",
        context_scope or "none",
        top_k if top_k is not None else "none",
        query_preview,
    )


def to_relevant_context(chunk: dict[str, Any], score: float) -> dict[str, Any]:
    line_range = chunk.get("line_range") if isinstance(chunk.get("line_range"), list) else []
    start_line = chunk.get("start_line")
    end_line = chunk.get("end_line")

    if start_line is None and len(line_range) >= 1:
        start_line = line_range[0]
    if end_line is None and len(line_range) >= 2:
        end_line = line_range[1]

    return {
        "file_path": chunk_file_path(chunk),
        "function_name": chunk_name(chunk),
        "content": chunk.get("content") or chunk.get("code") or "",
        "score": round(score, 4),
        "start_line": start_line,
        "end_line": end_line,
    }
