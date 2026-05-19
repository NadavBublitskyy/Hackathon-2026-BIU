"""Tests for Brain memory retrieval fallback behavior."""

import sys
import unittest
from pathlib import Path


BRAIN_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BRAIN_DIR.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BRAIN_DIR))

from backend.services import memory_retrieval_service as service  # noqa: E402


CODE_CHUNKS = [
    {
        "file_path": "main.py",
        "entity_name": "TaskFlowApp",
        "type": "Class",
        "content": "class TaskFlowApp:\n    def __init__(self):\n        self.auth = AuthManager()",
        "line_range": [1, 4],
    },
    {
        "file_path": "src/auth/manager.py",
        "entity_name": "verify_token",
        "type": "Function",
        "content": "def verify_token(token):\n    return jwt.decode(token, secret)",
        "line_range": [20, 22],
    },
    {
        "file_path": "src/utils/logger.py",
        "entity_name": "get_timestamped_log",
        "type": "Function",
        "content": "def get_timestamped_log(msg):\n    return msg",
        "line_range": [8, 9],
    },
]

STRUCTURE_JSON = {
    "files": {
        "main.py": {
            "type": "Logic/Engine",
            "language": "Python",
            "imports": ["src/auth/manager.py"],
            "chunks": [CODE_CHUNKS[0]],
        },
        "src/auth/manager.py": {
            "type": "Authentication",
            "language": "Python",
            "imports": ["src/utils/logger.py"],
            "chunks": [CODE_CHUNKS[1]],
        },
        "src/utils/logger.py": {
            "type": "Utility",
            "language": "Python",
            "imports": [],
            "chunks": [CODE_CHUNKS[2]],
        },
        "README.md": {
            "type": "Documentation",
            "language": "Markdown",
            "imports": [],
        },
        "package.json": {
            "type": "Configuration",
            "language": "JSON",
            "imports": [],
        },
    }
}


class MemoryRetrievalServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_chroma_ready = service.is_chroma_ready_for_chunks
        service.is_chroma_ready_for_chunks = lambda chunks: False

    def tearDown(self):
        service.is_chroma_ready_for_chunks = self.original_chroma_ready

    def test_bm25_fallback_prefers_named_symbol_match(self):
        result = service.retrieve_relevant_context_with_metadata(
            "Where is verify token decoded?",
            CODE_CHUNKS,
            structure_json=STRUCTURE_JSON,
        )

        self.assertEqual(result["retrieval_source"], "bm25")
        self.assertEqual(result["relevant_context"][0]["file_path"], "src/auth/manager.py")
        self.assertEqual(result["relevant_context"][0]["function_name"], "verify_token")

    def test_repo_wide_low_confidence_query_includes_anchor_files(self):
        result = service.retrieve_relevant_context_with_metadata(
            "what is the entire code flow?",
            CODE_CHUNKS,
            structure_json=STRUCTURE_JSON,
            context_scope=service.CONTEXT_SCOPE_REPO_WIDE,
        )

        paths = [item["file_path"] for item in result["relevant_context"]]
        self.assertEqual(result["retrieval_source"], "anchor_bm25")
        self.assertIn("main.py", paths)
        self.assertIn("README.md", paths)
        self.assertGreater(result["anchor_results"], 0)

    def test_selected_file_returns_only_that_files_chunks(self):
        result = service.retrieve_relevant_context_with_metadata(
            "explain this file",
            CODE_CHUNKS,
            selected_file_path="src/auth/manager.py",
            structure_json=STRUCTURE_JSON,
            context_scope=service.CONTEXT_SCOPE_SPECIFIC_CODE,
        )

        paths = [item["file_path"] for item in result["relevant_context"]]
        self.assertEqual(result["retrieval_source"], "selected_file_only")
        self.assertIn("src/auth/manager.py", paths)
        self.assertNotIn("main.py", paths)
        self.assertNotIn("src/utils/logger.py", paths)
        self.assertEqual(set(paths), {"src/auth/manager.py"})
        self.assertEqual(result["import_neighbor_results"], 0)


if __name__ == "__main__":
    unittest.main()
