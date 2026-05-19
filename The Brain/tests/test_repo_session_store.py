"""Tests for persisted repository session artifacts."""

import sys
import tempfile
import unittest
from pathlib import Path


BRAIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRAIN_DIR))

from backend.services import repo_session_store as store  # noqa: E402


class RepoSessionStoreTests(unittest.TestCase):
    def test_save_and_load_repo_session_artifacts(self):
        original_data_root = store.DATA_ROOT

        structure_json = {"files": [{"path": "main.py", "type": "Logic"}]}
        code_chunks_json = [{"file_path": "main.py", "content": "print('hello')"}]
        graph_data = {"nodes": [{"id": "main.py"}], "edges": []}
        repo_identity = {"project_name": "demo-repo", "core_keywords": ["demo"]}

        with tempfile.TemporaryDirectory() as temp_dir:
            store.DATA_ROOT = Path(temp_dir)
            try:
                repo_session_id = store.save_repo_session(
                    "https://github.com/example/demo-repo",
                    structure_json,
                    code_chunks_json,
                    graph_data,
                    repo_identity,
                )

                self.assertTrue(repo_session_id.startswith("demo-repo-"))
                self.assertEqual(store.load_structure_json(repo_session_id), structure_json)
                self.assertEqual(store.load_code_chunks_json(repo_session_id), code_chunks_json)
                self.assertEqual(store.load_graph_data(repo_session_id), graph_data)
                self.assertEqual(store.load_repo_identity(repo_session_id), repo_identity)
                self.assertEqual(store.load_repo_session(repo_session_id)["metadata"]["github_url"], "https://github.com/example/demo-repo")
            finally:
                store.DATA_ROOT = original_data_root


if __name__ == "__main__":
    unittest.main()
