"""This file builds context-aware LLM prompts from a user query, repo structure, and semantic code snippets."""

# Import Path so code snippets can get a useful language tag from their file extension.
from pathlib import Path
# Import Any so helpers can accept JSON structures with flexible shapes.
from typing import Any

# Store the system instruction that defines the LLM persona and accuracy rules.
CONTEXT_SYSTEM_PROMPT = """
You are an expert software architect helping a developer understand a codebase.

Use the provided repository structure and semantic code snippets as your source of truth.
Prioritize accuracy over guessing.
When the context includes file paths, mention the relevant file paths in your answer.
If the answer is not present in the provided context, say what is missing and what file or area should be inspected next.
Do not invent files, functions, imports, or APIs that are not supported by the context.
""".strip()

# Store the human prompt template that injects all context layers into one readable prompt.
CONTEXT_HUMAN_PROMPT = """
# Repo Structure (structure.json)

{repo_structure}

# Semantic Snippets (relevant_context)

{semantic_snippets}

# User Query

{user_query}
""".strip()

# Keep answer prompts focused without hard-coding a number of files.
MAX_RELEVANT_CONTEXT_CHARS = 12_000
MAX_SINGLE_SNIPPET_CHARS = 2_500
MIN_PROMPT_SNIPPET_SCORE = 0.40
RELATIVE_PROMPT_SCORE_THRESHOLD = 0.65


# Build the OpenAI-compatible message list used by the remote LLM API.
def build_context_aware_messages(user_query: str, structure_json: Any, relevant_context: Any) -> list[dict[str, str]]:
    # Convert the structure JSON into a readable Markdown-style tree.
    repo_structure = flatten_structure_json(structure_json)
    # Convert semantic snippets into path-labeled fenced code blocks.
    semantic_snippets = format_relevant_context(relevant_context)
    # Fill the human prompt template with the three context layers.
    human_prompt = CONTEXT_HUMAN_PROMPT.format(repo_structure=repo_structure, semantic_snippets=semantic_snippets, user_query=user_query.strip())
    # Return the system and user messages expected by the LLM connector.
    return [{"role": "system", "content": CONTEXT_SYSTEM_PROMPT}, {"role": "user", "content": human_prompt}]


# Build a single debug string that clearly shows every prompt layer.
def build_context_debug_prompt(user_query: str, structure_json: Any, relevant_context: Any) -> str:
    # Convert the exact outbound messages into one readable log string.
    messages = build_context_aware_messages(user_query, structure_json, relevant_context)
    # Return the debug prompt with clear layer headers.
    return "\n\n".join(f"## {message['role'].upper()}\n\n{message['content']}" for message in messages)


# Flatten structure.json into a Markdown-style list that the LLM can scan easily.
def flatten_structure_json(structure_json: Any) -> str:
    # Create the output line buffer.
    lines: list[str] = []
    # Recursively append readable structure lines from the JSON value.
    _append_structure_item(value=structure_json, lines=lines, depth=0, fallback_name="repo")
    # Return a fallback when the structure file is empty.
    if not lines:
        # Tell the model that no structure was provided.
        return "No repository structure was provided."
    # Join all collected lines into one Markdown block.
    return "\n".join(lines)


# Recursively append one structure JSON value into the output line buffer.
def _append_structure_item(value: Any, lines: list[str], depth: int, fallback_name: str) -> None:
    # Build indentation that preserves nesting visually.
    indent = "  " * depth
    # Handle arrays by appending each child item.
    if isinstance(value, list):
        # Iterate over every item in the array.
        for index, item in enumerate(value):
            # Append each child with the same depth because lists are collections, not folders.
            _append_structure_item(value=item, lines=lines, depth=depth, fallback_name=f"item_{index}")
        # Stop after handling the list.
        return
    # Handle objects by reading common file/tree fields.
    if isinstance(value, dict):
        # Read the best display name for this node.
        name = _first_text_value(value, ("file_path", "path", "name", "folder", "directory", "module")) or fallback_name
        # Read an optional type label from the structure object.
        node_type = _first_text_value(value, ("type", "kind"))
        # Read imports from common import fields.
        imports = value.get("imports") or value.get("imported_modules") or value.get("dependencies") or []
        # Normalize import values into text.
        import_text = _format_imports(imports)
        # Read definitions such as classes, functions, and variables from structure.json.
        definitions = value.get("definitions") or {}
        # Normalize definition values into readable text.
        definition_text = _format_definitions(definitions)
        # Add the base node line.
        line = f"{indent}- {name}"
        # Add the type label when it exists.
        if node_type:
            # Append the type in parentheses.
            line = f"{line} ({node_type})"
        # Add import information when it exists.
        if import_text:
            # Append import details after the file path.
            line = f"{line} imports: {import_text}"
        # Add definitions when the structure object includes them.
        if definition_text:
            # Append class/function/variable definitions after imports.
            line = f"{line} definitions: {definition_text}"
        # Store the formatted node line.
        lines.append(line)
        # Iterate over common child collection keys.
        for child_key in ("children", "files", "folders", "directories", "items"):
            # Read the child collection from the object.
            child_value = value.get(child_key)
            # Append child values when the key exists and is not empty.
            if child_value:
                # Recursively append child structure one level deeper.
                _append_structure_item(value=child_value, lines=lines, depth=depth + 1, fallback_name=child_key)
        # Stop after handling the object.
        return
    # Handle primitive values by adding them directly.
    lines.append(f"{indent}- {fallback_name}: {value}")


# Return the first non-empty text value from a dictionary for the given keys.
def _first_text_value(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    # Check each possible key in priority order.
    for key in keys:
        # Read the raw value from the dictionary.
        value = data.get(key)
        # Return stripped text values.
        if isinstance(value, str) and value.strip():
            # Return the cleaned text value.
            return value.strip()
    # Return an empty string when none of the keys had useful text.
    return ""


# Convert import data into a compact comma-separated string.
def _format_imports(imports: Any) -> str:
    # Return stripped text when imports are already a string.
    if isinstance(imports, str):
        # Return the cleaned string.
        return imports.strip()
    # Convert list-like import data into comma-separated text.
    if isinstance(imports, list):
        # Convert every import item into text and drop empty values.
        values = [str(item).strip() for item in imports if str(item).strip()]
        # Return the imports as one compact string.
        return ", ".join(values)
    # Return an empty string for unsupported import data shapes.
    return ""


# Convert definition data into a compact readable string.
def _format_definitions(definitions: Any) -> str:
    # Handle the common structure shape: {"classes": [], "functions": [], "variables": []}.
    if isinstance(definitions, dict):
        # Create a buffer for each populated definition category.
        parts: list[str] = []
        # Iterate over the known definition categories in a stable order.
        for label in ("classes", "functions", "variables"):
            # Read the values for this definition category.
            values = definitions.get(label) or []
            # Keep only non-empty text values.
            cleaned_values = [str(value).strip() for value in values if str(value).strip()]
            # Add this category when it contains values.
            if cleaned_values:
                # Append the category label and comma-separated values.
                parts.append(f"{label}: {', '.join(cleaned_values)}")
        # Join populated categories into one readable definition string.
        return "; ".join(parts)
    # Handle list-like definition data if a future ingestor returns a simple array.
    if isinstance(definitions, list):
        # Convert each value into clean text.
        values = [str(value).strip() for value in definitions if str(value).strip()]
        # Join all definitions into one compact string.
        return ", ".join(values)
    # Return an empty string for unsupported definition shapes.
    return ""


# Format relevant_context into path-labeled fenced code snippets.
def format_relevant_context(relevant_context: Any) -> str:
    # Normalize the relevant context input into a list of snippet dictionaries.
    snippets = _select_prompt_snippets(_normalize_snippets(relevant_context))
    # Return a fallback when no snippets were provided.
    if not snippets:
        # Tell the model that no semantic snippets were available.
        return "No semantic snippets were provided."
    # Create the output block buffer.
    blocks: list[str] = []
    # Iterate over snippets with a human-readable index.
    for index, snippet in enumerate(snippets, start=1):
        # Read the best file path value from the snippet.
        file_path = _first_text_value(snippet, ("file_path", "path", "filename", "file")) or "unknown_file"
        # Read the optional function name from the snippet.
        function_name = _first_text_value(snippet, ("function_name", "name", "symbol"))
        # Read the code/content value from the snippet.
        content = _fit_snippet_content(str(snippet.get("content") or snippet.get("code") or snippet.get("text") or ""))
        # Build the snippet header with a file path and optional function name.
        header = f"### Snippet {index}: {file_path}"
        # Add the function name when present.
        if function_name:
            # Append the function name to the header.
            header = f"{header} :: {function_name}"
        # Pick a code fence language from the file extension.
        language = _language_for_path(file_path)
        # Add the formatted snippet block.
        blocks.append(f"{header}\n```{language}\n{_escape_code_fence(content)}\n```")
    # Join all snippet blocks with blank lines.
    return "\n\n".join(blocks)


# Select snippets for the final LLM prompt by score and character budget, not by file count.
def _select_prompt_snippets(snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Return quickly when no snippets were supplied.
    if not snippets:
        return []

    # Sort scored snippets by relevance while preserving original order for unscored snippets.
    indexed_snippets = list(enumerate(snippets))
    scored_values = [_parse_score(snippet.get("score")) for _, snippet in indexed_snippets]
    usable_scores = [score for score in scored_values if score is not None]

    if usable_scores:
        best_score = max(usable_scores)
        minimum_score = max(MIN_PROMPT_SNIPPET_SCORE, best_score * RELATIVE_PROMPT_SCORE_THRESHOLD)
        indexed_snippets = [
            (index, snippet)
            for index, snippet in indexed_snippets
            if (score := _parse_score(snippet.get("score"))) is not None and score >= minimum_score
        ]
        indexed_snippets.sort(key=lambda item: (_parse_score(item[1].get("score")) or 0.0, -item[0]), reverse=True)

    selected: list[dict[str, Any]] = []
    used_chars = 0

    for _, snippet in indexed_snippets:
        content = str(snippet.get("content") or snippet.get("code") or snippet.get("text") or "")
        snippet_cost = min(len(content), MAX_SINGLE_SNIPPET_CHARS)

        if selected and used_chars + snippet_cost > MAX_RELEVANT_CONTEXT_CHARS:
            continue

        selected.append(snippet)
        used_chars += snippet_cost

        if used_chars >= MAX_RELEVANT_CONTEXT_CHARS:
            break

    return selected


# Trim a single snippet so one large file cannot dominate the prompt budget.
def _fit_snippet_content(content: str) -> str:
    # Keep short snippets unchanged.
    cleaned = content.strip()
    if len(cleaned) <= MAX_SINGLE_SNIPPET_CHARS:
        return cleaned

    # Return a clear truncation marker after the retained source prefix.
    return f"{cleaned[:MAX_SINGLE_SNIPPET_CHARS].rstrip()}\n... snippet truncated for prompt budget ..."


# Parse optional relevance scores.
def _parse_score(score: Any) -> float | None:
    # Missing scores should not affect score-threshold filtering.
    if score is None:
        return None

    try:
        return float(score)
    except (TypeError, ValueError):
        return None


# Normalize relevant_context into a list of snippet dictionaries.
def _normalize_snippets(relevant_context: Any) -> list[dict[str, Any]]:
    # Return dictionaries inside a list directly.
    if isinstance(relevant_context, list):
        # Keep only dictionary snippets.
        return [item for item in relevant_context if isinstance(item, dict)]
    # Handle objects that wrap snippets under common keys.
    if isinstance(relevant_context, dict):
        # Check common collection keys used by retrieval layers.
        for key in ("relevant_context", "chunks", "snippets", "results"):
            # Read the candidate collection.
            value = relevant_context.get(key)
            # Return normalized snippets from the collection when it is a list.
            if isinstance(value, list):
                # Keep only dictionary snippets.
                return [item for item in value if isinstance(item, dict)]
        # Treat a single dictionary with content as one snippet.
        if any(key in relevant_context for key in ("content", "code", "text")):
            # Wrap the single snippet in a list.
            return [relevant_context]
    # Return an empty list for unsupported shapes.
    return []


# Pick a Markdown code fence language from a file path.
def _language_for_path(file_path: str) -> str:
    # Read the lowercase file extension.
    suffix = Path(file_path).suffix.lower()
    # Map common extensions to Markdown language names.
    language_by_suffix = {".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript", ".tsx": "tsx", ".json": "json", ".md": "markdown", ".yml": "yaml", ".yaml": "yaml", ".html": "html", ".css": "css"}
    # Return the known language or an empty language tag.
    return language_by_suffix.get(suffix, "")


# Escape nested triple backticks so snippets cannot break the prompt fence format.
def _escape_code_fence(content: str) -> str:
    # Replace triple backticks with triple single quotes to preserve readable content.
    return content.replace("```", "'''").strip()
