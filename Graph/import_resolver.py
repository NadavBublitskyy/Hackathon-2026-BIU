from typing import Optional


SUPPORTED_EXTENSIONS = (".py", ".js", ".jsx", ".ts", ".tsx", ".java")
INDEX_FILENAMES = tuple(f"index{extension}" for extension in SUPPORTED_EXTENSIONS)


def normalize_file_path(path: str) -> str:
    """Normalize repo-relative paths for graph IDs and import matching."""
    normalized = path.replace("\\", "/").strip()
    parts = [part for part in normalized.split("/") if part and part != "."]
    return "/".join(parts)


def resolve_import(import_path: str, internal_file_paths: set[str]) -> Optional[str]:
    """
    Resolve an import string to an internal file path.

    Returns None for external libraries, unknown modules, and unresolved imports.
    """
    if not isinstance(import_path, str) or not import_path.strip():
        return None

    normalized_import = normalize_file_path(import_path.strip())
    normalized_files = {normalize_file_path(path) for path in internal_file_paths}

    if normalized_import in normalized_files:
        return normalized_import

    candidates = _build_candidates(normalized_import)

    for candidate in candidates:
        if candidate in normalized_files:
            return candidate

    for candidate in candidates:
        suffix_matches = [path for path in normalized_files if path.endswith(f"/{candidate}")]
        if len(suffix_matches) == 1:
            return suffix_matches[0]

    return None


def _build_candidates(import_path: str) -> list[str]:
    candidates: list[str] = []

    if "/" in import_path:
        path_import = import_path
    else:
        path_import = import_path.replace(".", "/")

    _add_path_candidates(candidates, path_import)

    if "." in import_path and "/" not in import_path:
        parts = import_path.split(".")
        for end_index in range(len(parts) - 1, 0, -1):
            _add_path_candidates(candidates, "/".join(parts[:end_index]))

    return candidates


def _add_path_candidates(candidates: list[str], base_path: str) -> None:
    if _has_supported_extension(base_path):
        _append_unique(candidates, base_path)
        return

    for extension in SUPPORTED_EXTENSIONS:
        _append_unique(candidates, f"{base_path}{extension}")

    for index_filename in INDEX_FILENAMES:
        _append_unique(candidates, f"{base_path}/{index_filename}")


def _has_supported_extension(path: str) -> bool:
    return path.endswith(SUPPORTED_EXTENSIONS)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
