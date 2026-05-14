from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Memory.api import router


def create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    return TestClient(app)


def test_memory_index_success(client: TestClient) -> None:
    with patch("Memory.api.index_code_chunks") as mock_index_code_chunks:
        response = client.post(
            "/memory/index",
            json={"json_file_path": "Memory/mock_code_chunks.json"},
        )

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Indexed code chunks successfully"
    assert data["indexed_chunks"] == 5

    mock_index_code_chunks.assert_called_once()


def test_memory_index_empty_path(client: TestClient) -> None:
    response = client.post(
        "/memory/index",
        json={"json_file_path": ""},
    )

    assert response.status_code == 400


def test_memory_index_invalid_path(client: TestClient) -> None:
    response = client.post(
        "/memory/index",
        json={"json_file_path": "Memory/non_existing_file.json"},
    )

    assert response.status_code == 400


def test_memory_retrieve_success(client: TestClient) -> None:
    mock_snippets = [
        {
            "path": "auth.py",
            "code": "class AuthManager:\n    pass",
            "score": 0.91,
            "chunk_id": "ch_1",
            "name": "AuthManager",
            "type": "class",
            "scope": "global",
            "start_line": 1,
            "end_line": 2,
        }
    ]

    with patch("Memory.api.index_code_chunks"), patch(
        "Memory.api.retrieve_snippets",
        return_value=mock_snippets,
    ) as mock_retrieve_snippets:
        index_response = client.post(
            "/memory/index",
            json={"json_file_path": "Memory/mock_code_chunks.json"},
        )
        response = client.post(
            "/memory/retrieve",
            json={"query": "How does authentication work?"},
        )

    assert index_response.status_code == 200
    assert response.status_code == 200

    data = response.json()
    assert "snippets" in data
    assert isinstance(data["snippets"], list)

    for snippet in data["snippets"]:
        assert "path" in snippet
        assert "code" in snippet
        assert "score" in snippet
        assert "chunk_id" in snippet

    mock_retrieve_snippets.assert_called_once_with("How does authentication work?")


def test_memory_retrieve_empty_query(client: TestClient) -> None:
    response = client.post(
        "/memory/retrieve",
        json={"query": ""},
    )

    assert response.status_code == 400


def test_memory_retrieve_unrelated_query(client: TestClient) -> None:
    with patch("Memory.api.retrieve_snippets", return_value=[]):
        response = client.post(
            "/memory/retrieve",
            json={"query": "How does the payment system process credit cards?"},
        )

    assert response.status_code == 200

    data = response.json()
    assert "snippets" in data
    assert isinstance(data["snippets"], list)


def run_tests() -> None:
    client = create_test_client()

    test_memory_index_success(client)
    test_memory_index_empty_path(client)
    test_memory_index_invalid_path(client)
    test_memory_retrieve_success(client)
    test_memory_retrieve_empty_query(client)
    test_memory_retrieve_unrelated_query(client)

    print("Memory API tests passed!")
    print("Run with: python -m Memory.test_api")


if __name__ == "__main__":
    run_tests()
