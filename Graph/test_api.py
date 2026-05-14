from fastapi import FastAPI
from fastapi.testclient import TestClient

from Graph.api import router


def create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_post_graph_returns_graph_data_for_valid_structure():
    client = create_test_client()

    response = client.post(
        "/graph",
        json={
            "files": [
                {"path": "src/main.py", "imports": ["src.utils.logger"]},
                {"path": "src/utils/logger.py"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["edges"] == [
        {
            "source": "src/main.py",
            "target": "src/utils/logger.py",
            "type": "import",
        }
    ]
    assert [node["id"] for node in response.json()["nodes"]] == [
        "src/main.py",
        "src/utils/logger.py",
    ]
    assert all("definitions" not in node for node in response.json()["nodes"])


def test_post_graph_with_empty_json_returns_empty_graph():
    client = create_test_client()

    response = client.post("/graph", json={})

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "edges": []}


def test_router_can_be_imported_and_included_without_side_effects():
    app = FastAPI()
    app.include_router(router)

    routes = [route.path for route in app.routes]

    assert "/graph" in routes


def test_post_node_details_returns_full_metadata():
    client = create_test_client()

    response = client.post(
        "/graph/node-details",
        json={
            "structure": {
                "files": [
                    {
                        "path": "src/auth/login.py",
                        "definitions": {
                            "classes": ["Authenticator"],
                            "functions": ["verify_token"],
                            "variables": ["MAX_RETRIES"],
                        },
                    }
                ]
            },
            "node_id": "src/auth/login.py",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "src/auth/login.py",
        "label": "login.py",
        "group": "auth",
        "definitions": {
            "classes": ["Authenticator"],
            "functions": ["verify_token"],
            "variables": ["MAX_RETRIES"],
        },
    }


def test_post_node_details_missing_definitions_returns_defaults():
    client = create_test_client()

    response = client.post(
        "/graph/node-details",
        json={
            "structure": {"files": [{"path": "src/auth/login.py"}]},
            "node_id": "src/auth/login.py",
        },
    )

    assert response.status_code == 200
    assert response.json()["definitions"] == {
        "classes": [],
        "functions": [],
        "variables": [],
    }


def test_post_node_details_unknown_node_returns_404():
    client = create_test_client()

    response = client.post(
        "/graph/node-details",
        json={
            "structure": {"files": [{"path": "src/main.py"}]},
            "node_id": "src/missing.py",
        },
    )

    assert response.status_code == 404


def test_post_node_details_missing_or_invalid_node_id_returns_400():
    client = create_test_client()

    missing_response = client.post(
        "/graph/node-details",
        json={"structure": {"files": [{"path": "src/main.py"}]}},
    )
    invalid_response = client.post(
        "/graph/node-details",
        json={"structure": {"files": [{"path": "src/main.py"}]}, "node_id": 123},
    )

    assert missing_response.status_code == 400
    assert invalid_response.status_code == 400


def test_post_node_details_invalid_request_body_types_return_400():
    client = create_test_client()

    list_response = client.post("/graph/node-details", json=["bad"])
    null_response = client.post("/graph/node-details", json=None)
    number_response = client.post("/graph/node-details", json=123)

    assert list_response.status_code == 400
    assert null_response.status_code == 400
    assert number_response.status_code == 400


def test_post_node_details_invalid_structure_returns_400():
    client = create_test_client()

    response = client.post(
        "/graph/node-details",
        json={"structure": "bad", "node_id": "src/main.py"},
    )

    assert response.status_code == 400


def test_post_node_details_empty_structure_returns_404():
    client = create_test_client()

    response = client.post(
        "/graph/node-details",
        json={"structure": {}, "node_id": "src/main.py"},
    )

    assert response.status_code == 404
