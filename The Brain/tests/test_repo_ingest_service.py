import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BRAIN_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BRAIN_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BRAIN_DIR))

from backend.services import repo_ingest_service  # noqa: E402


class RepoIngestServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_public_repo_uses_ingestor_and_graph_builder(self):
        structure_json = {
            "project_name": "repo",
            "total_files": 2,
            "files": [
                {"path": "src/main/Main.java", "imports": ["src/game/Game.java"]},
                {"path": "src/game/Game.java", "imports": []},
            ],
        }
        code_chunks_json = [{"chunk_id": "ch_1", "file_path": "src/main/Main.java"}]
        graph_data = {
            "nodes": [{"id": "src/main/Main.java"}, {"id": "src/game/Game.java"}],
            "edges": [{"source": "src/main/Main.java", "target": "src/game/Game.java", "type": "import"}],
        }

        with patch.object(repo_ingest_service, "ingest_repo", return_value={"structure_json": structure_json, "code_chunks_json": code_chunks_json}) as mock_ingest:
            with patch.object(repo_ingest_service, "build_graph", return_value=graph_data) as mock_build_graph:
                result = await repo_ingest_service.ingest_public_repo("https://github.com/owner/repo")

        mock_ingest.assert_called_once_with("https://github.com/owner/repo")
        mock_build_graph.assert_called_once_with(structure_json)
        self.assertEqual(
            {key: result[key] for key in ("structure_json", "code_chunks_json", "graph_data")},
            {"structure_json": structure_json, "code_chunks_json": code_chunks_json, "graph_data": graph_data},
        )
        self.assertEqual(result["repo_identity"]["project_name"], "repo")
        self.assertIn("repo", result["repo_identity"]["identity_sentence"])
        self.assertFalse(hasattr(repo_ingest_service, "build_graph_data"))

    async def test_ingest_public_repo_returns_graph_edges_for_internal_imports(self):
        structure_json = {
            "project_name": "repo",
            "total_files": 2,
            "files": [
                {"path": "src/main/Main.java", "imports": ["src/game/Game.java"]},
                {"path": "src/game/Game.java", "imports": []},
            ],
        }

        with patch.object(repo_ingest_service, "ingest_repo", return_value={"structure_json": structure_json, "code_chunks_json": []}):
            result = await repo_ingest_service.ingest_public_repo("https://github.com/owner/repo")

        self.assertEqual(
            result["graph_data"]["edges"],
            [{"source": "src/main/Main.java", "target": "src/game/Game.java", "type": "import"}],
        )


if __name__ == "__main__":
    unittest.main()
