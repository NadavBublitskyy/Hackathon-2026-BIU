from pathlib import PurePosixPath
from typing import Any, Optional

import networkx as nx

from Graph.import_resolver import normalize_file_path, resolve_import


EMPTY_DEFINITIONS = {
    "classes": [],
    "functions": [],
    "variables": [],
}


def build_graph(structure: dict) -> dict:
    """
    Build a file-level dependency graph from a Milestone 1 structure object.

    The graph is represented internally as a NetworkX DiGraph and exported as a
    JSON-serializable dictionary for frontend and Brain consumers.
    """
    graph = nx.DiGraph()
    files = structure.get("files", []) if isinstance(structure, dict) else []

    if not isinstance(files, list):
        return {"nodes": [], "edges": []}

    relevant_files = _collect_relevant_files(files)
    internal_paths = set(relevant_files)

    for file_data in files:
        if not isinstance(file_data, dict):
            continue

        file_path = _get_file_path(file_data)
        if file_path is None or file_path not in internal_paths:
            continue

        if graph.has_node(file_path):
            continue

        graph.add_node(
            file_path,
            label=_get_label(file_data, file_path),
            group=_get_group(file_path),
            definitions=_get_definitions(file_data),
        )

    for file_data in files:
        if not isinstance(file_data, dict):
            continue

        source = _get_file_path(file_data)
        if source is None or source not in internal_paths:
            continue

        for import_path in _get_imports(file_data):
            target = resolve_import(import_path, internal_paths)
            if target is not None and target != source:
                graph.add_edge(source, target, type="import")

    return _export_graph(graph)


def _collect_relevant_files(files: list[dict]) -> list[str]:
    paths: list[str] = []

    for file_data in files:
        if not isinstance(file_data, dict):
            continue

        file_path = _get_file_path(file_data)
        if file_path is not None and file_path not in paths:
            paths.append(file_path)

    return paths


def _get_file_path(file_data: dict) -> Optional[str]:
    path = file_data.get("path") or file_data.get("file_path") or file_data.get("id")
    if not isinstance(path, str) or not path.strip():
        return None

    return normalize_file_path(path.strip())


def _get_label(file_data: dict, file_path: str) -> str:
    name = file_data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()

    return PurePosixPath(file_path).name


def _get_group(file_path: str) -> str:
    parts = PurePosixPath(file_path).parts

    if len(parts) >= 3:
        return parts[-2]

    if len(parts) == 2:
        return parts[0]

    return "root"


def _get_definitions(file_data: dict) -> dict:
    definitions = file_data.get("definitions")
    if not isinstance(definitions, dict):
        return _empty_definitions()

    return {
        key: definitions.get(key, []) if isinstance(definitions.get(key, []), list) else []
        for key in EMPTY_DEFINITIONS
    }


def _get_imports(file_data: dict) -> list[str]:
    imports = file_data.get("imports", [])
    if not isinstance(imports, list):
        return []

    import_paths = []
    for import_item in imports:
        import_path = _extract_import_path(import_item)
        if import_path is not None:
            import_paths.append(import_path)

    return import_paths


def _extract_import_path(import_item: Any) -> Optional[str]:
    if isinstance(import_item, str):
        return import_item

    if not isinstance(import_item, dict):
        return None

    for key in ("path", "module", "name", "source"):
        value = import_item.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return None


def _empty_definitions() -> dict:
    return {key: value.copy() for key, value in EMPTY_DEFINITIONS.items()}


def _export_graph(graph: nx.DiGraph) -> dict:
    return {
        "nodes": [
            {
                "id": node_id,
                "label": node_data["label"],
                "group": node_data["group"],
                "definitions": node_data["definitions"],
            }
            for node_id, node_data in graph.nodes(data=True)
        ],
        "edges": [
            {
                "source": source,
                "target": target,
                "type": edge_data["type"],
            }
            for source, target, edge_data in graph.edges(data=True)
        ],
    }
