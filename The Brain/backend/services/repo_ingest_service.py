"""This file owns public GitHub repository ingestion for the Dockerized app flow."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import asyncio so file-content downloads can run concurrently.
import asyncio
# Import logging so non-blocking Chroma startup failures can be diagnosed.
import logging
# Import re so imports and definitions can be extracted from source text.
import re
# Import Callable so ingestion can notify the route when chunks are available.
from collections.abc import Callable
# Import PurePosixPath so GitHub paths are handled consistently.
from pathlib import PurePosixPath
# Import Any so provider JSON can be typed flexibly.
from typing import Any

# Import httpx so the backend can call GitHub's public API without a token.
import httpx
# Import chunk normalization so the app can consume both legacy and tree-sitter chunks.
from Memory.chunk_adapter import normalize_chunk

# Define public GitHub URL validation for owner/repo pairs.
GITHUB_REPO_PATTERN = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$", re.IGNORECASE)
# Define code extensions that are safe and useful for repo exploration.
ALLOWED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php", ".cpp", ".c", ".h", ".hpp"}
# Define directories that should not be indexed.
IGNORED_PATH_PARTS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", "target", ".next", ".idea"}
# Define a conservative per-file size cap for fast hackathon ingestion.
MAX_FILE_BYTES = 120_000
# Define a conservative total file cap to avoid exhausting GitHub unauthenticated limits.
MAX_FILES = 160
# Create a logger for ingestion diagnostics.
logger = logging.getLogger(__name__)

# Ingest a public GitHub repository into structure, chunks, and graph dictionaries.
async def ingest_public_repo(github_url: str, on_code_chunks_ready: Callable[[list[dict[str, Any]]], Any] | None = None) -> dict[str, Any]:
    # Parse and validate the incoming GitHub repository URL.
    owner, repo = parse_github_repo_url(github_url)
    # Create a short-lived async HTTP client for GitHub public API calls.
    async with httpx.AsyncClient(timeout=30.0, headers={"Accept": "application/vnd.github+json", "User-Agent": "Repo-Explorer-Hackathon"}) as client:
        # Fetch repository metadata to prove the repo exists publicly.
        repo_data = await fetch_github_json(client, f"https://api.github.com/repos/{owner}/{repo}")
        # Reject private repositories because the app intentionally does not ask users for tokens.
        if repo_data.get("private"):
            # Raise a user-facing validation error.
            raise ValueError("Repository is private. Public repositories do not need a GitHub token.")
        # Read the default branch used for tree traversal.
        default_branch = repo_data.get("default_branch") or "main"
        # Fetch the recursive file tree for the default branch.
        tree_data = await fetch_github_json(client, f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1")
        # Select a bounded set of source-code files from the tree.
        file_items = select_code_files(tree_data.get("tree", []))[:MAX_FILES]
        # Download selected file contents from raw.githubusercontent.com.
        contents = await fetch_file_contents(client, owner, repo, default_branch, file_items)
    # Build Milestone 1 code_chunks.json from downloaded file contents.
    code_chunks_json = build_code_chunks_json(contents)
    # Start vector indexing as soon as chunks exist; structure/graph building can continue.
    if on_code_chunks_ready is not None:
        try:
            on_code_chunks_ready(code_chunks_json)
        except Exception:
            logger.exception("Failed to schedule ChromaDB indexing.")
    # Build Milestone 1 structure.json from downloaded file contents.
    structure_json = build_structure_json(repo, file_items, contents)
    # Build graph data for the frontend visualization.
    graph_data = build_graph_data(structure_json)
    # Return the exact data the frontend flow needs.
    return {"structure_json": structure_json, "code_chunks_json": code_chunks_json, "graph_data": graph_data}


# Parse a GitHub repository URL into owner and repository names.
def parse_github_repo_url(github_url: str) -> tuple[str, str]:
    # Match the URL against the public GitHub repo pattern.
    match = GITHUB_REPO_PATTERN.match(github_url.strip())
    # Reject invalid GitHub URLs.
    if not match:
        # Raise a user-facing validation error.
        raise ValueError("Invalid GitHub repository URL.")
    # Extract owner and repo from the URL.
    owner, repo = match.groups()
    # Return the clean owner and repo names.
    return owner, repo.removesuffix(".git")


# Fetch JSON from GitHub and convert HTTP failures into clear errors.
async def fetch_github_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    # Send the GET request to GitHub.
    response = await client.get(url)
    # Convert not found into a public/private repo message.
    if response.status_code == 404:
        # Raise a user-facing validation error.
        raise ValueError("Repository was not found publicly on GitHub.")
    # Convert rate limiting into a clear retry message.
    if response.status_code in {403, 429}:
        # Raise a user-facing rate limit error.
        raise ValueError("GitHub rate limit blocked ingestion. Try again later.")
    # Raise for any other failed status.
    response.raise_for_status()
    # Return the decoded JSON body.
    return response.json()


# Select source-code files from the GitHub tree response.
def select_code_files(tree_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Prepare the filtered file list.
    selected_files = []
    # Iterate over all recursive tree items.
    for item in tree_items:
        # Keep blobs only because tree entries are directories.
        if item.get("type") != "blob":
            # Skip non-file entries.
            continue
        # Read the repository-relative file path.
        path = item.get("path", "")
        # Skip invalid or ignored file paths.
        if not is_indexable_path(path):
            # Continue to the next tree item.
            continue
        # Skip very large files.
        if int(item.get("size") or 0) > MAX_FILE_BYTES:
            # Continue to the next tree item.
            continue
        # Store the file item for content download.
        selected_files.append(item)
    # Return selected code files.
    return selected_files


# Decide whether a file path should be indexed.
def is_indexable_path(path: str) -> bool:
    # Split the path into POSIX parts.
    parts = PurePosixPath(path).parts
    # Reject ignored folders anywhere in the path.
    if any(part in IGNORED_PATH_PARTS for part in parts):
        # Return false for ignored generated/dependency paths.
        return False
    # Read the lowercase extension.
    extension = PurePosixPath(path).suffix.lower()
    # Keep only supported code extensions.
    return extension in ALLOWED_EXTENSIONS


# Fetch raw file contents concurrently with a small concurrency limit.
async def fetch_file_contents(client: httpx.AsyncClient, owner: str, repo: str, branch: str, file_items: list[dict[str, Any]]) -> dict[str, str]:
    # Create a semaphore to avoid too many simultaneous GitHub raw requests.
    semaphore = asyncio.Semaphore(8)

    # Fetch one raw file and return its path/content pair.
    async def fetch_one(item: dict[str, Any]) -> tuple[str, str | None]:
        # Read the repository-relative path.
        path = item["path"]
        # Build the raw.githubusercontent.com URL.
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        # Limit concurrency around the network call.
        async with semaphore:
            # Fetch the raw file content.
            response = await client.get(raw_url)
        # Skip files that cannot be downloaded.
        if response.status_code >= 400:
            # Return no content for failed raw downloads.
            return path, None
        # Return the downloaded source text.
        return path, response.text

    # Download all selected files.
    pairs = await asyncio.gather(*(fetch_one(item) for item in file_items))
    # Return only successfully downloaded text files.
    return {path: content for path, content in pairs if content is not None}


# Build structure.json from source files.
def build_structure_json(repo_name: str, file_items: list[dict[str, Any]], contents: dict[str, str]) -> dict[str, Any]:
    # Prepare each file entry for structure.json.
    files = []
    # Iterate over the GitHub tree files in stable order.
    for item in file_items:
        # Read the repository-relative path.
        path = item["path"]
        # Skip files whose content failed to download.
        if path not in contents:
            # Continue to the next file.
            continue
        # Read source text.
        content = contents[path]
        # Add the structure entry.
        files.append({"path": path, "name": PurePosixPath(path).name, "size_bytes": len(content.encode("utf-8")), "imports": extract_imports(path, content), "definitions": extract_definitions(path, content)})
    # Return the Milestone 1 structure object.
    return {"project_name": repo_name, "total_files": len(files), "files": files}


# Build code_chunks.json from source files.
def build_code_chunks_json(contents: dict[str, str]) -> list[dict[str, Any]]:
    # Prepare the chunks list.
    chunks = []
    # Track numeric chunk order.
    chunk_index = 1
    # Iterate over source files.
    for file_path, content in contents.items():
        # Extract symbol chunks from the file.
        file_chunks = extract_chunks(file_path, content)
        # Fall back to one file-level chunk when no functions/classes are found.
        if not file_chunks and content.strip():
            # Create a short file-level chunk.
            file_chunks = [{"type": "file", "name": PurePosixPath(file_path).name, "scope": "global", "content": trim_lines(content, 1, 80), "start_line": 1, "end_line": min(len(content.splitlines()), 80)}]
        # Add stable app-compatible chunk fields.
        for chunk in file_chunks:
            # Normalize old regex chunks and new tree-sitter chunks into one internal shape.
            normalized_chunk = normalize_chunk({"file_path": file_path, **chunk}, chunk_index)
            if normalized_chunk is not None:
                # Add the normalized chunk expected by Memory and Brain.
                chunks.append(normalized_chunk)
                # Increment the chunk ID counter only for accepted chunks.
                chunk_index += 1
    # Return the complete code_chunks.json list.
    return chunks


# Extract import strings from source text.
def extract_imports(file_path: str, content: str) -> list[str]:
    # Pick syntax based on the file extension.
    extension = PurePosixPath(file_path).suffix.lower()
    # Prepare a unique ordered imports list.
    imports = []
    # Parse Python imports.
    if extension == ".py":
        # Match import x and from x import y.
        patterns = [r"^\s*import\s+([A-Za-z0-9_.,\s]+)", r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\s+"]
    # Parse JavaScript and TypeScript imports.
    elif extension in {".js", ".jsx", ".ts", ".tsx"}:
        # Match ES module imports and require calls.
        patterns = [r"from\s+['\"]([^'\"]+)['\"]", r"import\s+['\"]([^'\"]+)['\"]", r"require\(['\"]([^'\"]+)['\"]\)"]
    # Parse Java imports.
    elif extension == ".java":
        # Match import package.Class;.
        patterns = [r"^\s*import\s+([A-Za-z0-9_.*]+);"]
    # Use no import parsing for other languages.
    else:
        # Return an empty import list.
        return []
    # Run all import patterns.
    for pattern in patterns:
        # Find all matching import values.
        for match in re.finditer(pattern, content, re.MULTILINE):
            # Split comma-separated Python imports.
            for value in match.group(1).split(","):
                # Clean the import value.
                cleaned = value.strip().split(" as ")[0]
                # Add unique non-empty imports.
                if cleaned and cleaned not in imports:
                    # Store the import.
                    imports.append(cleaned)
    # Return unique imports.
    return imports


# Extract class, function, and variable definitions from source text.
def extract_definitions(file_path: str, content: str) -> dict[str, list[str]]:
    # Prepare definition buckets.
    definitions = {"classes": [], "functions": [], "variables": []}
    # Extract class declarations.
    class_patterns = [r"^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+)*class\s+([A-Za-z_][A-Za-z0-9_]*)", r"^\s*export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)"]
    # Extract function declarations across common languages.
    function_patterns = [r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("]
    # Extract obvious constants.
    variable_patterns = [r"^\s*([A-Z][A-Z0-9_]*)\s*=", r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*="]
    # Fill class definitions.
    definitions["classes"] = unique_regex_matches(class_patterns, content)
    # Fill function definitions.
    definitions["functions"] = unique_regex_matches(function_patterns, content)
    # Fill variable definitions.
    definitions["variables"] = unique_regex_matches(variable_patterns, content)[:20]
    # Return definition metadata.
    return definitions


# Return unique regex group matches from multiple patterns.
def unique_regex_matches(patterns: list[str], content: str) -> list[str]:
    # Prepare the ordered output list.
    values = []
    # Run each pattern.
    for pattern in patterns:
        # Find every match in multiline mode.
        for match in re.finditer(pattern, content, re.MULTILINE):
            # Read the first capture group.
            value = match.group(1)
            # Store unique values only.
            if value not in values:
                # Add the definition name.
                values.append(value)
    # Return unique values.
    return values


# Extract chunks around classes and functions.
def extract_chunks(file_path: str, content: str) -> list[dict[str, Any]]:
    # Prefer the tree-sitter chunker when its optional parser dependency is available.
    tree_sitter_chunks = extract_tree_sitter_chunks(file_path, content)
    if tree_sitter_chunks:
        return tree_sitter_chunks

    # Split source text into lines.
    lines = content.splitlines()
    # Find symbol start lines.
    symbols = find_symbols(content)
    # Prepare chunks.
    chunks = []
    # Iterate over symbols with index so the next symbol can bound the chunk.
    for index, symbol in enumerate(symbols):
        # Use the next symbol start as the end bound.
        next_start = symbols[index + 1]["line"] if index + 1 < len(symbols) else len(lines) + 1
        # Cap each snippet length for prompt safety.
        end_line = min(next_start - 1, symbol["line"] + 80, len(lines))
        # Extract the snippet text.
        snippet = trim_lines(content, symbol["line"], end_line)
        # Add the code chunk.
        chunks.append({"type": symbol["type"], "name": symbol["name"], "scope": "global", "content": snippet, "start_line": symbol["line"], "end_line": end_line})
    # Return extracted chunks.
    return chunks


# Extract chunks with the shared tree-sitter implementation from Ingestor.
def extract_tree_sitter_chunks(file_path: str, content: str) -> list[dict[str, Any]]:
    # Import lazily so local tooling and Docker builds can still run without the optional parser installed.
    try:
        from Ingestor.code_chunker import CodeChunker
    except Exception:
        return []

    try:
        return CodeChunker().chunk(content, file_path)
    except Exception:
        logger.exception("Tree-sitter code chunking failed for %s; falling back to regex chunking.", file_path)
        return []


# Find class and function symbols with line numbers.
def find_symbols(content: str) -> list[dict[str, Any]]:
    # Prepare symbol patterns with their chunk types.
    patterns = [
        (r"^\s*(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+)*class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
        (r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "function"),
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "function"),
        (r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", "function"),
        (
            r"^\s*(?:public|private|protected)?\s*(?:static\s+|final\s+|synchronized\s+|abstract\s+)*[A-Za-z_][A-Za-z0-9_<>\[\], ?]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*(?:throws\s+[A-Za-z0-9_.,\s]+)?\{",
            "function",
        ),
    ]
    # Prepare collected symbols.
    symbols = []
    # Run each pattern against the content.
    for pattern, symbol_type in patterns:
        # Find every symbol.
        for match in re.finditer(pattern, content, re.MULTILINE):
            # Calculate one-based line number.
            line_number = content.count("\n", 0, match.start()) + 1
            # Store the symbol.
            symbols.append({"name": match.group(1), "type": symbol_type, "line": line_number})
    # Return symbols in source order.
    return sorted(symbols, key=lambda item: item["line"])


# Extract a one-based inclusive range of lines.
def trim_lines(content: str, start_line: int, end_line: int) -> str:
    # Split source text into lines.
    lines = content.splitlines()
    # Return the requested line range.
    return "\n".join(lines[start_line - 1:end_line])


# Build graph data in the Nodes & Links shape used by the frontend.
def build_graph_data(structure_json: dict[str, Any]) -> dict[str, Any]:
    # Read files from structure.json.
    files = structure_json.get("files", [])
    # Prepare nodes.
    nodes = [{"id": file["path"], "label": file["name"], "group": group_for_path(file["path"]), "definitions": file.get("definitions", {})} for file in files]
    # Prepare known paths for import resolution.
    known_paths = {file["path"] for file in files}
    # Prepare edges.
    edges = []
    # Iterate over files and imports.
    for file in files:
        # Resolve each import to an internal file when possible.
        for import_value in file.get("imports", []):
            # Find the imported file path.
            target = resolve_import(import_value, known_paths)
            # Add an edge only for internal imports.
            if target and target != file["path"]:
                # Store the import edge.
                edges.append({"source": file["path"], "target": target, "type": "import"})
    # Return graph data.
    return {"nodes": nodes, "edges": edges}


# Return the display group for a file path.
def group_for_path(file_path: str) -> str:
    # Split path parts.
    parts = PurePosixPath(file_path).parts
    # Use parent folder when present.
    return parts[-2] if len(parts) >= 2 else "root"


# Resolve an import string to an internal file path.
def resolve_import(import_value: str, known_paths: set[str]) -> str | None:
    # Normalize dotted imports into path-like text.
    normalized = import_value.replace(".", "/").strip("/")
    # Try common direct matches.
    candidates = [import_value, normalized, f"{normalized}.py", f"{normalized}.js", f"{normalized}.ts", f"{normalized}.tsx", f"{normalized}/index.js", f"{normalized}/index.ts"]
    # Return the first exact candidate.
    for candidate in candidates:
        # Check exact path match.
        if candidate in known_paths:
            # Return resolved path.
            return candidate
    # Fall back to suffix matching.
    for path in known_paths:
        # Check suffix match for package-like imports.
        if path.endswith(f"/{normalized}.py") or path.endswith(f"/{normalized}.js") or path.endswith(f"/{normalized}.ts"):
            # Return resolved path.
            return path
    # Return None when the import is external.
    return None
