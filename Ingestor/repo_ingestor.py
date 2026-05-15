import os
import re
from pathlib import PurePosixPath
from typing import Any

from Ingestor.github_ingestor import GitHubIngestor
from Ingestor.project_analyzer import ProjectAnalyzer


def ingest_repo(github_url: str) -> dict[str, Any]:
    ingestor = GitHubIngestor()
    repo_data = ingestor.get_repository_files(github_url)

    if "error" in repo_data:
        raise ValueError(repo_data["error"])

    files = repo_data.get("files", [])
    analyzer = ProjectAnalyzer(files)
    contents = _fetch_contents(ingestor, repo_data["owner"], repo_data["repo"], files)

    structure_json = _build_structure_json(repo_data["repo"], files, contents, analyzer)
    code_chunks_json = build_code_chunks_json(contents)

    return {
        "structure_json": structure_json,
        "code_chunks_json": code_chunks_json,
    }


def _fetch_contents(ingestor: GitHubIngestor, owner: str, repo_name: str, files: list[dict[str, Any]]) -> dict[str, str]:
    contents = {}

    for file_data in files:
        path = file_data.get("path")
        sha = file_data.get("sha")
        if not path or not sha:
            continue

        content = ingestor.get_file_content(owner, repo_name, sha)
        if content is not None:
            contents[path] = content

    return contents


def _build_structure_json(repo_name: str, files: list[dict[str, Any]], contents: dict[str, str], analyzer: ProjectAnalyzer) -> dict[str, Any]:
    structure_files = []

    for file_data in files:
        path = file_data.get("path")
        if not path or path not in contents:
            continue

        content = contents[path]
        extension = os.path.splitext(path)[1].lower()
        raw_imports = analyzer.extract_imports(content, extension)

        structure_files.append(
            {
                "path": path,
                "name": file_data.get("name") or PurePosixPath(path).name,
                "size_bytes": file_data.get("size_bytes") or len(content.encode("utf-8")),
                "type": analyzer.tag_metadata(path),
                "language": analyzer._LANGUAGE_MAP.get(extension, "Unknown"),
                "imports": analyzer._resolve_internal_dependencies(raw_imports, extension, path),
                "definitions": extract_definitions(content),
            }
        )

    return {
        "project_name": repo_name,
        "total_files": len(structure_files),
        "hierarchy": analyzer.build_hierarchy(),
        "files": structure_files,
    }


def build_code_chunks_json(contents: dict[str, str]) -> list[dict[str, Any]]:
    chunks = []
    chunk_index = 1

    for file_path, content in contents.items():
        file_chunks = extract_chunks(content)
        if not file_chunks and content.strip():
            file_chunks = [
                {
                    "type": "file",
                    "name": PurePosixPath(file_path).name,
                    "scope": "global",
                    "content": trim_lines(content, 1, min(len(content.splitlines()), 80)),
                    "start_line": 1,
                    "end_line": min(len(content.splitlines()), 80),
                }
            ]

        for chunk in file_chunks:
            chunks.append({"chunk_id": f"ch_{chunk_index}", "file_path": file_path, **chunk})
            chunk_index += 1

    return chunks


def extract_definitions(content: str) -> dict[str, list[str]]:
    return {
        "classes": _unique_regex_matches([r"^\s*(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)", r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", r"^\s*export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)"], content),
        "functions": _unique_regex_matches([r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("], content),
        "variables": _unique_regex_matches([r"^\s*([A-Z][A-Z0-9_]*)\s*=", r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*="], content)[:20],
    }


def extract_chunks(content: str) -> list[dict[str, Any]]:
    lines = content.splitlines()
    symbols = find_symbols(content)
    chunks = []

    for index, symbol in enumerate(symbols):
        next_start = symbols[index + 1]["line"] if index + 1 < len(symbols) else len(lines) + 1
        end_line = min(next_start - 1, symbol["line"] + 80, len(lines))
        chunks.append(
            {
                "type": symbol["type"],
                "name": symbol["name"],
                "scope": "global",
                "content": trim_lines(content, symbol["line"], end_line),
                "start_line": symbol["line"],
                "end_line": end_line,
            }
        )

    return chunks


def find_symbols(content: str) -> list[dict[str, Any]]:
    patterns = [
        (r"^\s*(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
        (r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)", "class"),
        (r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "function"),
        (r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", "function"),
        (r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(", "function"),
    ]
    symbols = []

    for pattern, symbol_type in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            symbols.append({"name": match.group(1), "type": symbol_type, "line": content.count("\n", 0, match.start()) + 1})

    return sorted(symbols, key=lambda item: item["line"])


def trim_lines(content: str, start_line: int, end_line: int) -> str:
    return "\n".join(content.splitlines()[start_line - 1:end_line])


def _unique_regex_matches(patterns: list[str], content: str) -> list[str]:
    values = []

    for pattern in patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            value = match.group(1)
            if value not in values:
                values.append(value)

    return values
