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
