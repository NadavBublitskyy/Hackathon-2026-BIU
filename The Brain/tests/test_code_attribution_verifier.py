"""Tests for verifying LLM file citations against structure.json."""

# Import json so tests can load the mock structure file.
import json
# Import sys so the backend package can be imported from the Brain directory.
import sys
# Import unittest for the test cases.
import unittest
# Import Path so mock file paths can be resolved reliably.
from pathlib import Path


# Resolve the Brain directory.
BRAIN_DIR = Path(__file__).resolve().parents[1]
# Resolve the repository root directory.
ROOT_DIR = BRAIN_DIR.parent
# Add The Brain folder to Python's import path.
sys.path.insert(0, str(BRAIN_DIR))

# Import the verifier under test.
from backend.code_attribution import CodeAttributionVerifier  # noqa: E402


# Store the mock structure path used by the tests.
STRUCTURE_MOCK_PATH = ROOT_DIR / "Ingestor" / "mocks" / "structure_mock.json"


# Load JSON from disk.
def load_json(path: Path):
    # Open the JSON file with UTF-8 encoding.
    with path.open(encoding="utf-8") as file:
        # Return the parsed JSON value.
        return json.load(file)


# Define tests for code attribution verification.
class CodeAttributionVerifierTests(unittest.TestCase):
    # Load the shared structure mock before each test.
    def setUp(self):
        # Store the parsed structure mock on the test instance.
        self.structure = load_json(STRUCTURE_MOCK_PATH)

    # Verify that valid file citations pass.
    def test_valid_paths_return_true(self):
        # Simulate an LLM response that cites real files from structure_mock.json.
        llm_output = "Implement this in src/auth/manager.py and reuse src/database/handler.py."
        # Assert that every mentioned path exists.
        self.assertTrue(CodeAttributionVerifier.verify_response_paths(self.structure, llm_output))

    # Verify that hallucinated file citations fail.
    def test_invalid_path_returns_false(self):
        # Simulate an LLM response that cites a file not present in structure_mock.json.
        llm_output = "Add the helper in utils/helper.py."
        # Assert that the hallucinated path is rejected.
        self.assertFalse(CodeAttributionVerifier.verify_response_paths(self.structure, llm_output))

    # Verify that mixed valid and invalid citations fail.
    def test_mixed_valid_and_invalid_paths_return_false(self):
        # Simulate an LLM response with one real path and one hallucinated path.
        llm_output = "Use main.py, then add new code in src/missing/service.py."
        # Assert that one invalid path makes the whole response unverified.
        self.assertFalse(CodeAttributionVerifier.verify_response_paths(self.structure, llm_output))

    # Verify that answers without file citations pass.
    def test_no_paths_returns_true(self):
        # Simulate an LLM response with no file path citation.
        llm_output = "The provided context is not enough to answer safely."
        # Assert that no citations means no hallucinated paths were found.
        self.assertTrue(CodeAttributionVerifier.verify_response_paths(self.structure, llm_output))

    # Verify that the static method can also accept a path to structure.json.
    def test_structure_path_input_is_supported(self):
        # Simulate an LLM response that cites a real file.
        llm_output = "The function is in src/utils/logger.py."
        # Assert that passing a JSON file path works.
        self.assertTrue(CodeAttributionVerifier.verify_response_paths(STRUCTURE_MOCK_PATH, llm_output))


# Run this file directly with python when needed.
if __name__ == "__main__":
    # Start unittest's test runner.
    unittest.main()
