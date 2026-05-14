"""This file owns LLM-based prompt category classification for frontend routing."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import asyncio so the classifier call can be bounded by a timeout.
import asyncio
# Import dataclass so classification results can be returned clearly.
from dataclasses import dataclass

# Import the singleton LLM connector used for classifier calls.
from backend.llm_client import get_llm_connector

# Define the classifier categories accepted by the frontend flow.
GENERAL = "GENERAL"
SPECIFIC_CODE = "SPECIFIC_CODE"
REPO_WIDE = "REPO_WIDE"

# Define the category labels returned to the UI.
CATEGORY_LABELS = {
    GENERAL: "General",
    SPECIFIC_CODE: "Specific code",
    REPO_WIDE: "Repo-wide",
}

# Define the category values used by the React app.
FRONTEND_CATEGORY_VALUES = {
    GENERAL: "general",
    SPECIFIC_CODE: "specific_code",
    REPO_WIDE: "repo_wide",
}

# Define the strict system instruction for the cheap LLM classifier.
PROMPT_CLASSIFIER_SYSTEM_PROMPT = """
You are a high-precision intent classifier for a repository explorer. Categorize the user query into exactly one of the three categories below.

### CATEGORIES
1. GENERAL: Greetings, general programming theory (e.g., "What is an interface?"), or talking to the AI. No repository context is required.
2. SPECIFIC_CODE: Use ONLY for queries that name an EXPLICIT, IDENTIFIED entity. The user must provide a specific filename, function name, class name, or API route (e.g., "auth.py", "validateUser()", or "GET /login").
3. REPO_WIDE: Use for queries about the codebase holistically, architecturally, or vaguely. This includes any reference to "the code," "here," "this project," "the repo," "the codebase," or "where is..." style questions.

### CRITICAL MAPPING RULES
- References like "the code," "here," "this," "in here," or "the logic" MUST be classified as REPO_WIDE.
- Architectural questions ("How does data flow?") are REPO_WIDE.
- If and only if a specific symbol or file is named, use SPECIFIC_CODE.

### EXAMPLES
- "Explain the code here" -> REPO_WIDE
- "What does the code do?" -> REPO_WIDE
- "How does this project handle auth?" -> REPO_WIDE
- "Where is the database initialized?" -> REPO_WIDE
- "Look at the code in main.py and explain it" -> SPECIFIC_CODE
- "What is the purpose of the handle_request function?" -> SPECIFIC_CODE
- "How do I write a for-loop in Python?" -> GENERAL

### OUTPUT RULES
- Return exactly one string: GENERAL, SPECIFIC_CODE, or REPO_WIDE.
- Do not explain. Do not use punctuation. Do not use quotes.
""".strip()

# Define a short timeout so classification cannot make the UI feel stuck.
CLASSIFICATION_TIMEOUT_SECONDS = 4.0


# Store one prompt classification result.
@dataclass(frozen=True)
class PromptClassificationResult:
    # Store the frontend category value.
    category: str
    # Store the display label for the category.
    label: str
    # Store the raw classifier category string.
    classifier_category: str
    # Store the model used for classification.
    classifier_model: str
    # Store the raw model response for debugging.
    raw_classifier_response: str
    # Store whether the local fallback was used.
    used_local_fallback: bool
    # Store a short reason for debugging and UI metadata.
    reason: str


# Classify a prompt by calling a cheap LLM model.
async def classify_prompt(prompt: str, selected_file_path: str | None, classifier_model_name: str) -> PromptClassificationResult:
    # Build the strict OpenAI-compatible messages for classification.
    messages = build_classifier_messages(prompt, selected_file_path)
    # Try the cheap LLM classifier first.
    try:
        # Send the prompt to the requested classifier model with deterministic settings.
        result = await asyncio.wait_for(get_llm_connector().send_messages(messages=messages, temperature=0.0, max_tokens=8, model_name=classifier_model_name), timeout=CLASSIFICATION_TIMEOUT_SECONDS)
        # Read the raw classifier response.
        raw_response = result.message.strip()
        # Parse the response into one accepted category.
        classifier_category = parse_classifier_category(raw_response)
        # Fall back locally when the model ignores the exact-output contract.
        if classifier_category is None:
            # Choose a deterministic local category.
            classifier_category = classify_prompt_locally(prompt, selected_file_path)
            # Return fallback metadata.
            return build_result(classifier_category, classifier_model_name, raw_response, True, "LLM classifier returned an invalid category, so local fallback was used.")
        # Return LLM classifier metadata.
        return build_result(classifier_category, classifier_model_name, raw_response, False, "Classified by the prompt classification LLM.")
    # Fall back locally when the classifier model is unavailable.
    except Exception as exc:
        # Choose a deterministic local category so the app can continue.
        classifier_category = classify_prompt_locally(prompt, selected_file_path)
        # Return fallback metadata without exposing credentials or provider internals.
        return build_result(classifier_category, classifier_model_name, f"LOCAL_FALLBACK: {exc.__class__.__name__}", True, "Classifier LLM failed, so local fallback was used.")


# Build the strict classifier messages.
def build_classifier_messages(prompt: str, selected_file_path: str | None) -> list[dict[str, str]]:
    # Build selected-file context for the classifier.
    selected_file_text = selected_file_path or "none"
    # Build the user message with the prompt and graph selection.
    user_message = f"""
User prompt:
{prompt.strip()}

Selected graph file:
{selected_file_text}

Return exactly one category:
GENERAL
SPECIFIC_CODE
REPO_WIDE
""".strip()
    # Return the system and user messages.
    return [{"role": "system", "content": PROMPT_CLASSIFIER_SYSTEM_PROMPT}, {"role": "user", "content": user_message}]


# Parse the classifier response into one category.
def parse_classifier_category(response: str) -> str | None:
    # Normalize common quote/code-fence/punctuation wrappers.
    cleaned = response.strip().splitlines()[0].strip().strip("\"'`.,;:") if response.strip() else ""
    # Return the cleaned category when it is valid.
    if cleaned in {GENERAL, SPECIFIC_CODE, REPO_WIDE}:
        # Use the exact valid category.
        return cleaned
    # Detect noisy responses that contain exactly one valid category.
    matches = [category for category in (GENERAL, SPECIFIC_CODE, REPO_WIDE) if category in response]
    # Accept noisy text only when it mentions exactly one category.
    if len(matches) == 1:
        # Return the only category found.
        return matches[0]
    # Return None when the response is not trustworthy.
    return None


# Classify locally only as a fallback when the LLM classification is unavailable.
def classify_prompt_locally(prompt: str, selected_file_path: str | None) -> str:
    # Route selected graph-file questions to specific-code context.
    if selected_file_path:
        # Return specific-code because the user selected a concrete file.
        return SPECIFIC_CODE
    # Normalize prompt text.
    lowered = prompt.lower()
    # Route repo-wide questions.
    if any(term in lowered for term in ("repo", "repository", "architecture", "data flow", "dependencies", "all files", "codebase", "implement", "feature", "refactor", "rewrite", "debug", "bug", "where should", "how do i add")):
        # Return repo-wide because the question needs broader context.
        return REPO_WIDE
    # Route file/symbol questions.
    if any(term in lowered for term in ("where is", "which file", "specific file", "function", "class", "method", "endpoint", "route", "handler", "import", ".py", ".js", ".ts", ".tsx")):
        # Return specific-code because the question points at code symbols or paths.
        return SPECIFIC_CODE
    # Default to general when no repo/code cues are present.
    return GENERAL


# Build the frontend response object.
def build_result(classifier_category: str, classifier_model_name: str, raw_response: str, used_local_fallback: bool, reason: str) -> PromptClassificationResult:
    # Return the structured result.
    return PromptClassificationResult(category=FRONTEND_CATEGORY_VALUES[classifier_category], label=CATEGORY_LABELS[classifier_category], classifier_category=classifier_category, classifier_model=classifier_model_name, raw_classifier_response=raw_response, used_local_fallback=used_local_fallback, reason=reason)
