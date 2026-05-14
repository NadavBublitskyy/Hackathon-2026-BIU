"""Integration tests that send Ingestor mock context to a real LLM provider."""

import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path


BRAIN_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BRAIN_DIR.parent
sys.path.insert(0, str(BRAIN_DIR))

from backend.llm_blueprint import build_context_aware_messages  # noqa: E402


STRUCTURE_MOCK_PATH = ROOT_DIR / "Ingestor" / "mocks" / "structure_mock.json"
CODE_CHUNKS_MOCK_PATH = ROOT_DIR / "Ingestor" / "mocks" / "code_chanks_mock.json"
ENV_PATH = ROOT_DIR / ".env"


def load_json(path: Path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value

    if not ENV_PATH.exists():
        return ""

    with ENV_PATH.open(encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"').strip("'")

    return ""


def call_openrouter(messages: list[dict[str, str]], max_tokens: int = 120) -> str:
    api_key = load_env_value("OPENROUTER_API_KEY") or load_env_value("LLM_API_KEY")
    if not api_key:
        raise unittest.SkipTest("OPENROUTER_API_KEY or LLM_API_KEY is required for real LLM tests.")

    base_url = load_env_value("LLM_BASE_URL") or "https://openrouter.ai/api/v1"
    model = load_env_value("LLM_MODEL_NAME") or "openrouter/auto"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "Repo Explorer Tests",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"LLM provider returned HTTP {exc.code}: {detail}") from exc

    choices = body.get("choices") or []
    if not choices:
        raise AssertionError(f"LLM provider returned no choices: {body}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AssertionError(f"LLM provider returned no text content: {body}")

    return content.strip()


class BrainRealLLMResponseTests(unittest.TestCase):
    def setUp(self):
        self.structure = load_json(STRUCTURE_MOCK_PATH)
        self.code_chunks = load_json(CODE_CHUNKS_MOCK_PATH)

    def test_real_llm_identifies_verify_token_file(self):
        messages = build_context_aware_messages(
            "Answer with only the exact file path where verify_token is implemented.",
            self.structure,
            self.code_chunks,
        )

        response = call_openrouter(messages)

        self.assertIn("src/auth/manager.py", response)

    def test_real_llm_identifies_task_saving_feature_file(self):
        messages = build_context_aware_messages(
            "Answer with only the exact file path where a task-saving feature should be implemented.",
            self.structure,
            self.code_chunks,
        )

        response = call_openrouter(messages)

        self.assertIn("src/database/handler.py", response)


if __name__ == "__main__":
    unittest.main()
