import json

from Graph.graph_builder import build_graph


DEFAULT_DEFINITIONS = {
    "classes": [],
    "functions": [],
    "variables": [],
}


def test_empty_input_returns_empty_graph():
    assert build_graph({}) == {"nodes": [], "edges": []}
    assert build_graph({"files": []}) == {"nodes": [], "edges": []}


def test_files_that_is_not_a_list_returns_empty_graph():
    assert build_graph({"files": "bad"}) == {"nodes": [], "edges": []}


def test_invalid_file_entries_are_ignored():
    graph = build_graph(
        {
            "files": [
                None,
                "bad",
                123,
                {},
                {"path": ""},
                {"path": "src/main.py"},
            ]
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["src/main.py"]
    assert graph["edges"] == []


def test_file_missing_imports_produces_node_with_no_edges():
    graph = build_graph(
        {
            "files": [
                {
                    "path": "src/main.py",
                    "definitions": {"classes": [], "functions": ["main"], "variables": []},
                }
            ]
        }
    )

    assert graph["nodes"] == [
        {
            "id": "src/main.py",
            "label": "main.py",
            "group": "src",
            "definitions": {"classes": [], "functions": ["main"], "variables": []},
        }
    ]
    assert graph["edges"] == []


def test_file_missing_definitions_uses_defaults():
    graph = build_graph({"files": [{"path": "src/auth/login.py", "imports": []}]})

    assert graph["nodes"][0]["definitions"] == DEFAULT_DEFINITIONS
    assert graph["edges"] == []


def test_partial_definitions_fill_missing_fields():
    graph = build_graph(
        {
            "files": [
                {
                    "path": "src/auth/login.py",
                    "definitions": {"functions": ["login"]},
                }
            ]
        }
    )

    assert graph["nodes"][0]["definitions"] == {
        "classes": [],
        "functions": ["login"],
        "variables": [],
    }


def test_unresolved_external_imports_are_ignored():
    graph = build_graph(
        {
            "files": [
                {
                    "path": "src/auth/login.py",
                    "imports": ["os", "jwt", "datetime", "fastapi", "react"],
                }
            ]
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["src/auth/login.py"]
    assert graph["edges"] == []


def test_duplicate_edges_are_removed():
    graph = build_graph(
        {
            "files": [
                {
                    "path": "src/main.py",
                    "imports": ["src.auth.manager", "src/auth/manager.py"],
                },
                {"path": "src/auth/manager.py"},
            ]
        }
    )

    assert graph["edges"] == [
        {
            "source": "src/main.py",
            "target": "src/auth/manager.py",
            "type": "import",
        }
    ]


def test_duplicate_variant_paths_create_one_normalized_node():
    graph = build_graph(
        {
            "files": [
                {"path": "./src/auth/login.py"},
                {"path": "src\\auth\\login.py"},
                {"path": "src/auth/login.py"},
            ]
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["src/auth/login.py"]


def test_duplicate_slashes_create_one_normalized_node():
    graph = build_graph(
        {
            "files": [
                {"path": "src//auth//login.py"},
                {"path": "src/auth/login.py"},
            ]
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["src/auth/login.py"]


def test_duplicate_normalized_nodes_do_not_overwrite_metadata():
    graph = build_graph(
        {
            "files": [
                {
                    "path": "./src/auth/login.py",
                    "definitions": {"classes": ["Original"], "functions": [], "variables": []},
                },
                {
                    "path": "src\\auth\\login.py",
                    "definitions": {"classes": ["Overwritten"], "functions": [], "variables": []},
                },
            ]
        }
    )

    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["id"] == "src/auth/login.py"
    assert graph["nodes"][0]["definitions"]["classes"] == ["Original"]


def test_self_imports_are_ignored():
    graph = build_graph(
        {
            "files": [
                {"path": "src/main.py", "imports": ["src.main", "src/main.py"]},
            ]
        }
    )

    assert [node["id"] for node in graph["nodes"]] == ["src/main.py"]
    assert graph["edges"] == []


def test_valid_internal_import_creates_edge_for_dotted_import():
    graph = build_graph(
        {
            "files": [
                {"path": "src/main.py", "imports": ["src.auth.manager"]},
                {"path": "src/auth/manager.py"},
            ]
        }
    )

    assert graph["edges"] == [
        {
            "source": "src/main.py",
            "target": "src/auth/manager.py",
            "type": "import",
        }
    ]


def test_valid_internal_import_creates_edge_for_file_path_import():
    graph = build_graph(
        {
            "files": [
                {"path": "src/main.py", "imports": ["src/auth/manager.py"]},
                {"path": "src/auth/manager.py"},
            ]
        }
    )

    assert graph["edges"] == [
        {
            "source": "src/main.py",
            "target": "src/auth/manager.py",
            "type": "import",
        }
    ]


def test_import_dict_format_with_module_key_creates_edge():
    graph = build_graph(
        {
            "files": [
                {"path": "src/main.py", "imports": [{"module": "src.auth.manager"}]},
                {"path": "src/auth/manager.py"},
            ]
        }
    )

    assert graph["edges"] == [
        {
            "source": "src/main.py",
            "target": "src/auth/manager.py",
            "type": "import",
        }
    ]


def test_import_dict_format_with_path_key_creates_edge():
    graph = build_graph(
        {
            "files": [
                {"path": "src/main.py", "imports": [{"path": "src/auth/manager.py"}]},
                {"path": "src/auth/manager.py"},
            ]
        }
    )

    assert graph["edges"] == [
        {
            "source": "src/main.py",
            "target": "src/auth/manager.py",
            "type": "import",
        }
    ]


def test_output_is_json_serializable():
    json.dumps(build_graph({"files": [{"path": "src/main.py"}]}))
