from __future__ import annotations

import os
import time

import httpx


_API_URL = "https://openrouter.ai/api/v1/embeddings"
_MODEL = "openai/text-embedding-3-small"
_BATCH_SIZE = 100
_MAX_RETRIES = 3
_RETRYABLE_STATUS_CODES = {429, 503}
_TIMEOUT_SECONDS = 60.0


class OpenRouterEmbeddingFunction:
    def __init__(self) -> None:
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLM_API_KEY", "")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY or LLM_API_KEY environment variable is required.")
        # Persistent client — reuses TCP connections across all batch requests.
        self._client = httpx.Client(
            base_url="https://openrouter.ai",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=_TIMEOUT_SECONDS,
        )

    def name(self) -> str:
        return "openrouter_embedding"

    def embed_query(self, input: str) -> list[float]:
        """Embed a single query string — sends a plain string, not a list."""
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.post(
                    "/api/v1/embeddings",
                    json={"model": _MODEL, "input": input},
                )
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_backoff(attempt))
                        continue
                    response.raise_for_status()
                if not response.is_success:
                    print(f"DEBUG embed_query 400 body: {response.text[:500]}", flush=True)
                response.raise_for_status()
                return response.json()["data"][0]["embedding"]
            except httpx.TimeoutException:
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(_backoff(attempt))
        raise RuntimeError("embed_query failed after all retries.")

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self.__call__(input)

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        """Embed one batch of strings with retry logic."""
        for attempt in range(_MAX_RETRIES):
            try:
                response = self._client.post(
                    "/api/v1/embeddings",
                    json={"model": _MODEL, "input": batch},
                )
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_backoff(attempt))
                        continue
                    response.raise_for_status()
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in data]
            except httpx.TimeoutException:
                if attempt == _MAX_RETRIES - 1:
                    raise
                time.sleep(_backoff(attempt))
        raise RuntimeError("Embedding batch failed after all retries.")

    def __call__(self, input: list[str]) -> list[list[float]]:
        """Embed all inputs, splitting into batches of _BATCH_SIZE."""
        if not input:
            return []
        if len(input) <= _BATCH_SIZE:
            return self._embed_batch(input)
        batches = [input[i:i + _BATCH_SIZE] for i in range(0, len(input), _BATCH_SIZE)]
        result: list[list[float]] = []
        for batch in batches:
            result.extend(self._embed_batch(batch))
        return result


def _backoff(attempt: int) -> float:
    return 1.0 * (attempt + 1)
