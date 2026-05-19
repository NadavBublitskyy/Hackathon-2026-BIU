"""Build a compact repository identity card for prompt routing."""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from backend.services.memory_retrieval_service import tokenize_terms


TECH_STACK_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "React",
    ".ts": "TypeScript",
    ".tsx": "React/TypeScript",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".h": "C/C++",
    ".hpp": "C++",
    ".md": "Markdown",
}

TECH_STACK_BY_FILE = {
    "containerfile": "Docker",
    "dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "package.json": "Node.js",
    "pom.xml": "Maven/Java",
    "build.gradle": "Gradle/Java",
    "settings.gradle": "Gradle/Java",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "vite.config.js": "Vite",
    "vite.config.ts": "Vite",
}

IDENTITY_KEYWORD_STOP_WORDS = {
    "app",
    "application",
    "code",
    "file",
    "files",
    "get",
    "main",
    "public",
    "repo",
    "repository",
    "set",
    "src",
    "test",
    "tests",
    "unknown",
}


def build_repo_identity_card(github_url: str, structure_json: dict[str, Any], code_chunks_json: list[dict[str, Any]]) -> dict[str, Any]:
    project_name = str(structure_json.get("project_name") or github_url.rstrip("/").split("/")[-1] or "repository")
    tech_stack = infer_tech_stack(structure_json)
    readme_summary = summarize_readme(code_chunks_json)
    core_keywords = infer_core_keywords(structure_json, code_chunks_json, readme_summary)

    fallback_summary = build_fallback_summary(project_name, tech_stack, core_keywords)
    summary = readme_summary or fallback_summary

    return {
        "project_name": project_name,
        "github_url": github_url,
        "tech_stack": tech_stack[:8],
        "core_keywords": core_keywords[:10],
        "readme_summary": summary,
        "identity_sentence": build_identity_sentence(project_name, tech_stack, core_keywords, summary),
    }


def infer_tech_stack(structure_json: dict[str, Any]) -> list[str]:
    counts: Counter[str] = Counter()

    for file_record in iter_structure_files(structure_json):
        path = str(file_record.get("path") or "")
        basename = PurePosixPath(path.lower()).name
        extension = os.path.splitext(path)[1].lower()
        language = str(file_record.get("language") or "").strip()

        if language and language.lower() != "unknown":
            counts[language] += 3
        if extension in TECH_STACK_BY_EXTENSION:
            counts[TECH_STACK_BY_EXTENSION[extension]] += 2
        if basename in TECH_STACK_BY_FILE:
            counts[TECH_STACK_BY_FILE[basename]] += 4

    return [name for name, _ in counts.most_common()]


def summarize_readme(code_chunks_json: list[dict[str, Any]]) -> str:
    readme_text = ""

    for chunk in code_chunks_json:
        file_path = str(chunk.get("file_path") or chunk.get("path") or "")
        basename = PurePosixPath(file_path.lower()).name
        if basename.startswith("readme") or basename in {"overview.md", "architecture.md"}:
            readme_text = f"{readme_text}\n{chunk.get('content') or chunk.get('code') or ''}"

    cleaned = clean_markdown(readme_text)
    if not cleaned:
        return ""

    sentences = split_sentences(cleaned)
    if len(sentences) >= 2:
        return " ".join(sentences[:2])[:600]
    return cleaned[:600]


def infer_core_keywords(structure_json: dict[str, Any], code_chunks_json: list[dict[str, Any]], readme_summary: str) -> list[str]:
    counts: Counter[str] = Counter()

    for file_record in iter_structure_files(structure_json):
        path = str(file_record.get("path") or "")
        file_type = str(file_record.get("type") or "")
        definitions = file_record.get("definitions") or {}

        add_weighted_terms(counts, path, 4)
        add_weighted_terms(counts, file_type, 3)

        if isinstance(definitions, dict):
            for values in definitions.values():
                if isinstance(values, list):
                    for value in values:
                        add_weighted_terms(counts, str(value), 3)

    for chunk in code_chunks_json:
        add_weighted_terms(counts, str(chunk.get("file_path") or ""), 3)
        add_weighted_terms(counts, str(chunk.get("name") or chunk.get("entity_name") or chunk.get("function_name") or ""), 4)
        add_weighted_terms(counts, str(chunk.get("type") or ""), 2)

    add_weighted_terms(counts, readme_summary, 2)

    return [
        term
        for term, _ in counts.most_common(20)
        if term not in IDENTITY_KEYWORD_STOP_WORDS and not term.isdigit()
    ][:10]


def add_weighted_terms(counts: Counter[str], value: str, weight: int) -> None:
    for term in tokenize_terms(value):
        if term not in IDENTITY_KEYWORD_STOP_WORDS and not term.isdigit():
            counts[term] += weight


def iter_structure_files(structure_json: dict[str, Any]) -> list[dict[str, Any]]:
    files = structure_json.get("files") if isinstance(structure_json, dict) else []
    if isinstance(files, dict):
        return [{"path": path, **record} for path, record in files.items() if isinstance(record, dict)]
    if isinstance(files, list):
        return [item for item in files if isinstance(item, dict)]
    return []


def clean_markdown(value: str) -> str:
    without_code = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    without_markup = re.sub(r"!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)", " ", without_code)
    without_headers = re.sub(r"^[#>\-*` ]+", " ", without_markup, flags=re.MULTILINE)
    compact = re.sub(r"\s+", " ", without_headers)
    return compact.strip()


def split_sentences(value: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", value) if sentence.strip()]


def build_fallback_summary(project_name: str, tech_stack: list[str], core_keywords: list[str]) -> str:
    stack_text = ", ".join(tech_stack[:3]) if tech_stack else "unknown stack"
    keyword_text = ", ".join(core_keywords[:5]) if core_keywords else "the parsed source files"
    return f"{project_name} is a {stack_text} repository. Its parsed source files focus on {keyword_text}."


def build_identity_sentence(project_name: str, tech_stack: list[str], core_keywords: list[str], summary: str) -> str:
    stack_text = ", ".join(tech_stack[:4]) if tech_stack else "unknown stack"
    keyword_text = ", ".join(core_keywords[:8]) if core_keywords else "parsed project code"
    return f"The current repository is {project_name}, a {stack_text} project focusing on {keyword_text}. {summary}"
