"""Tests for Brain prompt construction using the real Ingestor mock JSON files."""

import json
import sys
import unittest
from pathlib import Path


BRAIN_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BRAIN_DIR.parent
sys.path.insert(0, str(BRAIN_DIR))

from backend.llm_blueprint import (  # noqa: E402
    build_context_aware_messages,
    build_context_debug_prompt,
    flatten_structure_json,
    format_relevant_context,
)


STRUCTURE_MOCK_PATH = ROOT_DIR / "Ingestor" / "mocks" / "structure_mock.json"
CODE_CHUNKS_MOCK_PATH = ROOT_DIR / "Ingestor" / "mocks" / "code_chanks_mock.json"


def load_json(path: Path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


class BrainPromptConstructionTests(unittest.TestCase):
    def setUp(self):
        self.structure = load_json(STRUCTURE_MOCK_PATH)
        self.code_chunks = load_json(CODE_CHUNKS_MOCK_PATH)

    def test_function_location_question_injects_matching_file_and_snippet(self):
        prompt = build_context_debug_prompt(
            "In which file does the verify_token function exist?",
            self.structure,
            self.code_chunks,
        )

        self.assertIn("## SYSTEM", prompt)
        self.assertIn("# Repo Structure (structure.json)", prompt)
        self.assertIn("# Semantic Snippets (relevant_context)", prompt)
        self.assertIn("# User Query", prompt)
        self.assertIn("src/auth/manager.py", prompt)
        self.assertIn("functions: hash_password, verify_token", prompt)
        self.assertIn("### Snippet 3: src/auth/manager.py :: verify_token", prompt)
        self.assertIn("def verify_token(token):", prompt)

    def test_feature_location_question_injects_database_context(self):
        messages = build_context_aware_messages(
            "Where should I implement a feature that saves a new task?",
            self.structure,
            self.code_chunks,
        )

        system_message = messages[0]["content"]
        user_message = messages[1]["content"]

        self.assertIn("mention the relevant file paths", system_message)
        self.assertIn("src/database/handler.py", user_message)
        self.assertIn("classes: DBConnection, QueryBuilder", user_message)
        self.assertIn("### Snippet 4: src/database/handler.py :: save_task", user_message)
        self.assertIn("INSERT INTO tasks", user_message)

    def test_unknown_function_question_keeps_missing_context_instruction(self):
        messages = build_context_aware_messages(
            "In which file does the getName function exist?",
            self.structure,
            self.code_chunks,
        )

        self.assertIn("If the answer is not present", messages[0]["content"])
        self.assertIn("getName", messages[1]["content"])
        self.assertNotIn(":: getName", messages[1]["content"])

    def test_structure_flattening_preserves_imports_and_definitions(self):
        flattened = flatten_structure_json(self.structure)

        self.assertIn("main.py imports: src.auth.manager, src.database.handler, src.utils.logger", flattened)
        self.assertIn("classes: TaskFlowApp", flattened)
        self.assertIn("functions: initialize_system, shutdown", flattened)
        self.assertIn("src/constants.py definitions: variables: STATUS_SUCCESS, STATUS_ERROR, RETRY_LIMIT", flattened)

    def test_relevant_context_is_wrapped_in_path_labeled_code_fences(self):
        snippets = format_relevant_context(self.code_chunks)

        self.assertIn("### Snippet 1: main.py :: TaskFlowApp", snippets)
        self.assertIn("```python", snippets)
        self.assertIn("class TaskFlowApp:", snippets)
        self.assertIn("### Snippet 5: src/utils/logger.py :: get_timestamped_log", snippets)


if __name__ == "__main__":
    unittest.main()
