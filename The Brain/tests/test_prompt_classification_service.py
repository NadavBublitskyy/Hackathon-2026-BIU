"""Tests for LLM prompt route classification."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


BRAIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRAIN_DIR))

from backend.llm_errors import LLMError  # noqa: E402
from backend.services import prompt_classification_service as service  # noqa: E402


class FakeConnector:
    def __init__(self, message: str):
        self.message = message
        self.calls = []

    async def send_messages(self, messages, temperature=0.2, max_tokens=800, model_name=None):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "model_name": model_name,
            }
        )
        return SimpleNamespace(message=self.message, raw={}, model=model_name)


class FailingThenWorkingConnector:
    def __init__(self, first_error: Exception, second_message: str):
        self.first_error = first_error
        self.second_message = second_message
        self.calls = []

    async def send_messages(self, messages, temperature=0.2, max_tokens=800, model_name=None):
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "model_name": model_name,
            }
        )
        if len(self.calls) == 1:
            raise self.first_error
        return SimpleNamespace(message=self.second_message, raw={}, model=model_name)


class PromptClassificationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_classification_uses_llm_response_not_retrieved_context(self):
        connector = FakeConnector("REPO_WIDE")
        original_get_llm_connector = service.get_llm_connector
        service.get_llm_connector = lambda: connector

        try:
            result = await service.classify_prompt(
                "what is the entire code flow?",
                None,
                "classifier-model",
                retrieved_context=[{"file_path": "src/game/Constants.java", "score": 0.99}],
            )
        finally:
            service.get_llm_connector = original_get_llm_connector

        self.assertEqual(result.category, "repo_wide")
        self.assertFalse(result.used_local_fallback)
        self.assertEqual(connector.calls[0]["model_name"], "classifier-model")
        self.assertEqual(connector.calls[0]["temperature"], 0.0)
        self.assertNotIn("Constants.java", connector.calls[0]["messages"][1]["content"])

    async def test_repo_identity_is_injected_into_classifier_prompt(self):
        connector = FakeConnector("GENERAL")
        original_get_llm_connector = service.get_llm_connector
        original_load_repo_identity_for_classification = service.load_repo_identity_for_classification
        service.get_llm_connector = lambda: connector
        service.load_repo_identity_for_classification = lambda repo_session_id: {
            "project_name": "PhysicsEngine",
            "tech_stack": ["C++"],
            "core_keywords": ["collision", "aabb", "physics"],
            "readme_summary": "A physics engine focused on AABB collision detection.",
        }

        try:
            result = await service.classify_prompt("how does collision work?", None, "classifier-model", repo_session_id="repo-123")
        finally:
            service.get_llm_connector = original_get_llm_connector
            service.load_repo_identity_for_classification = original_load_repo_identity_for_classification

        user_message = connector.calls[0]["messages"][1]["content"]
        self.assertEqual(result.category, "general")
        self.assertIn("Project: PhysicsEngine", user_message)
        self.assertIn("Tech stack: C++", user_message)
        self.assertIn("collision", user_message)

    async def test_selected_file_bypasses_llm_classifier(self):
        connector = FakeConnector("SPECIFIC_CODE")
        original_get_llm_connector = service.get_llm_connector
        service.get_llm_connector = lambda: connector

        try:
            result = await service.classify_prompt("explain this file", "src/game/Constants.java", "classifier-model")
        finally:
            service.get_llm_connector = original_get_llm_connector

        self.assertEqual(result.category, "specific_code")
        self.assertEqual(result.raw_classifier_response, "SELECTED_FILE_RULE")
        self.assertEqual(connector.calls, [])

    async def test_selected_file_forces_specific_code_even_if_llm_would_say_general(self):
        connector = FakeConnector("GENERAL")
        original_get_llm_connector = service.get_llm_connector
        service.get_llm_connector = lambda: connector

        try:
            result = await service.classify_prompt("what is the main function of this file?", "src/game/Velocity.java", "classifier-model")
        finally:
            service.get_llm_connector = original_get_llm_connector

        self.assertEqual(result.category, "specific_code")
        self.assertEqual(result.classifier_category, service.SPECIFIC_CODE)
        self.assertEqual(connector.calls, [])

    async def test_invalid_llm_route_raises_instead_of_local_fallback(self):
        connector = FakeConnector("probably specific")
        original_get_llm_connector = service.get_llm_connector
        service.get_llm_connector = lambda: connector

        try:
            with self.assertRaises(LLMError):
                await service.classify_prompt("what is the entire code flow?", None, "classifier-model")
        finally:
            service.get_llm_connector = original_get_llm_connector

    def test_parser_accepts_common_route_formatting(self):
        self.assertEqual(service.parse_classifier_category("repo-wide."), service.REPO_WIDE)
        self.assertEqual(service.parse_classifier_category("specific code"), service.SPECIFIC_CODE)
        self.assertEqual(service.parse_classifier_category("GENERAL"), service.GENERAL)

    async def test_general_llm_route_is_overridden_when_repo_evidence_is_strong(self):
        connector = FakeConnector("GENERAL")
        original_get_llm_connector = service.get_llm_connector
        original_calculate_repo_match_signals = service.calculate_repo_match_signals
        service.get_llm_connector = lambda: connector
        service.calculate_repo_match_signals = lambda prompt, repo_session_id, repo_identity, topic_keywords, topic_match_keywords: service.RepoMatchSignals(
            canary_score=0.72,
            canary_file_path="src/collision/CollisionInfo.java",
            topic_keywords=("vector", "collision"),
            topic_match_keywords=("collision",),
        )

        try:
            result = await service.classify_prompt("How do I implement vector collision?", None, "classifier-model", repo_session_id="repo-123")
        finally:
            service.get_llm_connector = original_get_llm_connector
            service.calculate_repo_match_signals = original_calculate_repo_match_signals

        self.assertEqual(result.category, "repo_wide")
        self.assertEqual(result.classifier_category, service.REPO_WIDE)
        self.assertEqual(result.repo_relevance_score, 0.72)
        self.assertEqual(result.canary_file_path, "src/collision/CollisionInfo.java")

    async def test_generic_language_howto_stays_general_even_with_high_repo_score(self):
        connector = FakeConnector("GENERAL")
        original_get_llm_connector = service.get_llm_connector
        original_calculate_repo_match_signals = service.calculate_repo_match_signals
        service.get_llm_connector = lambda: connector
        service.calculate_repo_match_signals = lambda prompt, repo_session_id, repo_identity, topic_keywords, topic_match_keywords: service.RepoMatchSignals(
            canary_score=0.91,
            canary_file_path="src/game/Counter.java",
            topic_keywords=("fibonacci",),
            topic_match_keywords=(),
        )

        try:
            result = await service.classify_prompt(
                "how to implement a function in python that returns the n fibonacci number?",
                None,
                "classifier-model",
                repo_session_id="repo-123",
            )
        finally:
            service.get_llm_connector = original_get_llm_connector
            service.calculate_repo_match_signals = original_calculate_repo_match_signals

        self.assertEqual(result.category, "general")
        self.assertEqual(result.classifier_category, service.GENERAL)
        self.assertEqual(result.repo_relevance_score, 0.91)

    async def test_identity_topic_match_can_override_general_with_moderate_canary_score(self):
        connector = FakeConnector("GENERAL")
        original_get_llm_connector = service.get_llm_connector
        original_calculate_repo_match_signals = service.calculate_repo_match_signals
        service.get_llm_connector = lambda: connector
        service.calculate_repo_match_signals = lambda prompt, repo_session_id, repo_identity, topic_keywords, topic_match_keywords: service.RepoMatchSignals(
            canary_score=0.47,
            canary_file_path="src/collision/Collidable.java",
            topic_keywords=("vector", "collision"),
            topic_match_keywords=("collision",),
        )

        try:
            result = await service.classify_prompt("How do I implement vector collision?", None, "classifier-model", repo_session_id="repo-123")
        finally:
            service.get_llm_connector = original_get_llm_connector
            service.calculate_repo_match_signals = original_calculate_repo_match_signals

        self.assertEqual(result.category, "repo_wide")
        self.assertEqual(result.repo_relevance_score, 0.47)
        self.assertEqual(result.topic_match_keywords, ("collision",))

    async def test_classifier_model_failure_retries_configured_model(self):
        connector = FailingThenWorkingConnector(LLMError("No endpoints found"), "GENERAL")
        original_get_llm_connector = service.get_llm_connector
        original_get_settings = service.get_settings
        service.get_llm_connector = lambda: connector
        service.get_settings = lambda: SimpleNamespace(llm_model_name="openrouter/auto")

        try:
            result = await service.classify_prompt("hello", None, "missing-classifier-model")
        finally:
            service.get_llm_connector = original_get_llm_connector
            service.get_settings = original_get_settings

        self.assertEqual(result.category, "general")
        self.assertEqual(connector.calls[0]["model_name"], "missing-classifier-model")
        self.assertEqual(connector.calls[1]["model_name"], "openrouter/auto")
        self.assertIn("retried with openrouter/auto", result.reason)


if __name__ == "__main__":
    unittest.main()
