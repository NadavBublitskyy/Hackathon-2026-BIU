"""Integration tests that verify the FastAPI SSE endpoint streams a real LLM response."""

import json
import time
import unittest
import urllib.error
import urllib.request


STREAM_URL = "http://127.0.0.1:8080/api/chat/stream"


def open_streaming_chat(prompt: str):
    body = json.dumps({"prompt": prompt}).encode("utf-8")
    request = urllib.request.Request(
        STREAM_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        return urllib.request.urlopen(request, timeout=60)
    except urllib.error.URLError as exc:
        raise unittest.SkipTest(
            "The Brain backend must be running on http://127.0.0.1:8080 for streaming endpoint tests."
        ) from exc


class BrainRealLLMStreamingTests(unittest.TestCase):
    def test_chat_stream_endpoint_emits_real_llm_tokens_quickly(self):
        started_at = time.monotonic()
        first_token_seconds = None
        tokens: list[str] = []

        with open_streaming_chat("Write exactly this sentence: streaming works.") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/event-stream", response.headers.get("content-type", ""))

            current_event = None
            while True:
                line = response.readline().decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    current_event = line.removeprefix("event:").strip()
                    continue
                if not line.startswith("data:"):
                    continue

                payload = json.loads(line.removeprefix("data:").strip())

                if current_event == "token":
                    if first_token_seconds is None:
                        first_token_seconds = time.monotonic() - started_at
                    tokens.append(payload["token"])
                    if len("".join(tokens)) >= len("streaming works"):
                        break

                if current_event == "error":
                    self.fail(f"stream returned error event: {payload}")

                if current_event == "done":
                    break

        streamed_text = "".join(tokens).strip().lower()

        self.assertIsNotNone(first_token_seconds)
        self.assertLess(first_token_seconds, 1.5)
        self.assertIn("streaming", streamed_text)
        self.assertTrue(streamed_text)


if __name__ == "__main__":
    unittest.main()
