"""This file chooses which LLM model should answer a user prompt."""

# Enable Python 3.10-style type annotations when local tests run on Python 3.9.
from __future__ import annotations

# Import asyncio so the classifier call can be capped with a timeout.
import asyncio
# Import time so classification overhead can be measured.
import time
# Import dataclass so routing results can be returned as a small typed object.
from dataclasses import dataclass
# Import Any so the router can work with the existing connector without importing HTTP dependencies.
from typing import Any


# Define the default cheap model used only for intent classification.
DEFAULT_CLASSIFIER_MODEL_NAME = "openai/gpt-4o-mini"
# Define the maximum classifier wait with margin below the 500ms acceptance limit.
DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS = 0.4


# Define the system instruction sent to the cheap classifier model.
MATCH_MODEL_SYSTEM_PROMPT = """
You are a strict model router for a codebase assistant.

Your only job is to choose which model should answer the user's request.
You must return exactly one of the two allowed model names.
Do not explain.
Do not add punctuation.
Do not wrap the answer in quotes.
Do not return labels like EASY or HARD.

Choose the light model for simple navigation, file lookup, symbol lookup, or "where is this logic?" questions.
Choose the heavy model for refactoring, rewriting, debugging, architecture, data flow, feature design, security, performance, or implementation planning.
""".strip()


# Define a structured result for model routing decisions.
@dataclass(frozen=True)
class MatchModelResult:
    # Store the model name that should answer the user prompt.
    selected_model: str
    # Store the broad difficulty label for logging and frontend metadata.
    difficulty: str
    # Store the cheap model that was asked to classify the prompt.
    classifier_model: str
    # Store the raw classifier text for debugging.
    raw_classifier_response: str
    # Store how long classification took in milliseconds.
    classification_ms: float
    # Store whether the local keyword fallback was used instead of a clean classifier answer.
    used_local_fallback: bool


# Define the model matching class requested by the routing issue.
class MatchModel:
    # Initialize the router with the existing LLM connector and classifier settings.
    def __init__(self, connector: Any, classifier_model_name: str = DEFAULT_CLASSIFIER_MODEL_NAME, classification_timeout_seconds: float = DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS):
        # Save the connector so this class can call the remote LLM provider.
        self.connector = connector
        # Save the default cheap classifier model name.
        self.classifier_model_name = classifier_model_name
        # Save the timeout that prevents classification from adding too much latency.
        self.classification_timeout_seconds = classification_timeout_seconds

    # Return only the selected model name for callers that do not need routing metadata.
    async def match_model(self, user_prompt: str, light_model_name: str, heavy_model_name: str, classifier_model_name: str | None = None) -> str:
        # Run the full routing flow and keep the selected model.
        result = await self.choose_model(user_prompt, light_model_name, heavy_model_name, classifier_model_name=classifier_model_name)
        # Return the selected model string exactly as provided by the API caller.
        return result.selected_model

    # Classify a user prompt and return the selected model plus routing metadata.
    async def choose_model(self, user_prompt: str, light_model_name: str, heavy_model_name: str, classifier_model_name: str | None = None) -> MatchModelResult:
        # Choose the classifier model override when the API caller provides one.
        classifier_model = classifier_model_name or self.classifier_model_name
        # Build the strict prompt that forces the classifier to choose only one model name.
        messages = self.build_classifier_messages(user_prompt, light_model_name, heavy_model_name)
        # Start measuring routing overhead.
        started_at = time.perf_counter()
        # Prepare the raw classifier response for debugging.
        raw_response = ""
        # Track whether local keyword routing was needed.
        used_local_fallback = False
        # Try to classify with the cheap model first.
        try:
            # Send the classification request with zero temperature and a tiny token budget.
            result = await asyncio.wait_for(self.connector.send_messages(messages=messages, temperature=0.0, max_tokens=30, model_name=classifier_model), timeout=self.classification_timeout_seconds)
            # Read the classifier text from the provider result.
            raw_response = result.message
            # Parse the classifier response into one of the allowed model names.
            selected_model = self.parse_classifier_response(raw_response, light_model_name, heavy_model_name)
            # Fall back locally when the classifier ignored the strict output contract.
            if selected_model is None:
                # Mark that the local heuristic decided the model.
                used_local_fallback = True
                # Use deterministic keywords so the request can still continue.
                selected_model = self.classify_locally(user_prompt, light_model_name, heavy_model_name)
        # Fall back locally when the classifier model is unavailable or too slow.
        except Exception as exc:
            # Keep a safe debug marker without exposing secrets.
            raw_response = f"LOCAL_FALLBACK: {exc.__class__.__name__}"
            # Mark that local keyword routing decided the model.
            used_local_fallback = True
            # Use deterministic keywords so the request can still continue.
            selected_model = self.classify_locally(user_prompt, light_model_name, heavy_model_name)
        # Stop measuring routing overhead.
        classification_ms = (time.perf_counter() - started_at) * 1000
        # Convert the selected model into a simple difficulty label.
        difficulty = self.difficulty_for_model(selected_model, light_model_name, heavy_model_name)
        # Return the full routing result.
        return MatchModelResult(selected_model=selected_model, difficulty=difficulty, classifier_model=classifier_model, raw_classifier_response=raw_response.strip(), classification_ms=classification_ms, used_local_fallback=used_local_fallback)

    # Build the strict messages sent to the cheap classifier model.
    @staticmethod
    def build_classifier_messages(user_prompt: str, light_model_name: str, heavy_model_name: str) -> list[dict[str, str]]:
        # Build the user instruction with the exact allowed model strings.
        router_prompt = f"""
User prompt:
{user_prompt.strip()}

Allowed light model:
{light_model_name.strip()}

Allowed heavy model:
{heavy_model_name.strip()}

Return exactly one of these two strings:
{light_model_name.strip()}
{heavy_model_name.strip()}
""".strip()
        # Return the OpenAI-compatible message list.
        return [{"role": "system", "content": MATCH_MODEL_SYSTEM_PROMPT}, {"role": "user", "content": router_prompt}]

    # Parse the classifier output into one allowed model name.
    @staticmethod
    def parse_classifier_response(response: str, light_model_name: str, heavy_model_name: str) -> str | None:
        # Normalize the classifier output for exact comparison.
        cleaned = MatchModel.clean_classifier_text(response)
        # Return the light model when the classifier obeyed the contract exactly.
        if cleaned == light_model_name:
            # Use the caller-provided light model string.
            return light_model_name
        # Return the heavy model when the classifier obeyed the contract exactly.
        if cleaned == heavy_model_name:
            # Use the caller-provided heavy model string.
            return heavy_model_name
        # Detect whether the response contains only the light model inside extra text.
        light_found = light_model_name in response
        # Detect whether the response contains only the heavy model inside extra text.
        heavy_found = heavy_model_name in response
        # Accept a noisy response only when it mentions exactly one valid option.
        if light_found and not heavy_found:
            # Use the caller-provided light model string.
            return light_model_name
        # Accept a noisy response only when it mentions exactly one valid option.
        if heavy_found and not light_found:
            # Use the caller-provided heavy model string.
            return heavy_model_name
        # Return None when the classifier response cannot be trusted.
        return None

    # Clean punctuation and code fences that some models may add despite strict instructions.
    @staticmethod
    def clean_classifier_text(response: str) -> str:
        # Strip whitespace around the model response.
        cleaned = response.strip()
        # Remove a single Markdown code fence wrapper when present.
        if cleaned.startswith("```") and cleaned.endswith("```"):
            # Remove backticks and surrounding whitespace.
            cleaned = cleaned.strip("`").strip()
        # Keep only the first line because the router is supposed to answer with one line.
        cleaned = cleaned.splitlines()[0].strip() if cleaned else ""
        # Remove common quote and punctuation wrappers.
        return cleaned.strip().strip("\"'`.,;:")

    # Classify locally when the cheap LLM is unavailable, slow, or non-compliant.
    @staticmethod
    def classify_locally(user_prompt: str, light_model_name: str, heavy_model_name: str) -> str:
        # Normalize the prompt for keyword checks.
        prompt = user_prompt.lower().strip()
        # Route explicit implementation-planning questions to the heavy model.
        heavy_phrases = (
            "how do i rewrite",
            "how should i rewrite",
            "how do i refactor",
            "how should i refactor",
            "where should i implement",
            "how do i implement",
            "how should i implement",
            "explain the data flow",
            "explain architecture",
        )
        # Return the heavy model when a strong hard-task phrase is present.
        if any(phrase in prompt for phrase in heavy_phrases):
            # Use the caller-provided heavy model string.
            return heavy_model_name
        # Route direct file and symbol lookup questions to the light model.
        light_phrases = (
            "where is",
            "where are",
            "which file",
            "what file",
            "in which file",
            "find file",
            "find function",
            "locate",
        )
        # Return the light model when the prompt is clearly navigational.
        if any(phrase in prompt for phrase in light_phrases):
            # Use the caller-provided light model string.
            return light_model_name
        # Define broader hard-task words that usually need stronger reasoning.
        hard_words = (
            "refactor",
            "rewrite",
            "debug",
            "bug",
            "fix",
            "architecture",
            "architectural",
            "data flow",
            "design",
            "implement",
            "feature",
            "security",
            "performance",
            "optimize",
            "migration",
            "test strategy",
        )
        # Return the heavy model for prompts that contain hard-task vocabulary.
        if any(word in prompt for word in hard_words):
            # Use the caller-provided heavy model string.
            return heavy_model_name
        # Default to the light model for simple repo navigation and budget safety.
        return light_model_name

    # Convert the selected model into a user-facing difficulty label.
    @staticmethod
    def difficulty_for_model(selected_model: str, light_model_name: str, heavy_model_name: str) -> str:
        # Return HARD when the selected model is the caller-provided heavy model.
        if selected_model == heavy_model_name and heavy_model_name != light_model_name:
            # Mark the route as heavy.
            return "HARD"
        # Return EASY for the light model and for identical model-name edge cases.
        return "EASY"
