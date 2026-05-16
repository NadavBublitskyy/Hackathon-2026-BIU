"""This file owns LLM-based prompt category classification for frontend routing."""

# Enable Python 3.10-style type annotations when local tools run on Python 3.9.
from __future__ import annotations

# Import asyncio so the classifier call can be bounded by a timeout..
import asyncio
# Import re so fallback classification can detect code-specific language.
import re
# Import dataclass so classification results can be returned clearly.
from dataclasses import dataclass
# Import Any so retrieved context candidates can be typed flexibly.
from typing import Any

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
1. GENERAL: Use only when the user is asking a general programming/conversation question that does not need the loaded repository. If Memory found no relevant candidate files and there are no repo words, this may be GENERAL.
2. SPECIFIC_CODE: Use when the answer should focus on concrete code. This includes selected files, explicit filenames/functions/classes/routes, "which file/where is" questions, and Memory candidates whose relevance score is at or above the SPECIFIC_CODE score threshold after repo-wide intent has been ruled out.
3. REPO_WIDE: Use when the answer needs a broad view of the codebase, architecture, cross-file behavior, overall behavior, or vague repo context. Explicit repo-wide wording overrides Memory score unless the user selected/named a concrete file or symbol.

### CRITICAL MAPPING RULES
- Treat Memory candidate scores as repo evidence. If any Memory candidate has score >= 0.40, strongly prefer SPECIFIC_CODE even when the user did not name a file.
- Do not use the number of candidate files to decide SPECIFIC_CODE. One high-scoring file and many high-scoring files both mean SPECIFIC_CODE.
- Do not let Memory score override explicit whole-repo wording such as "the whole repo", "architecture", "overall", "this project", "codebase", or "what does this repo do".
- General-looking implementation questions must be checked against Memory evidence. For example, "How do I implement a Circle class?" is SPECIFIC_CODE if Memory found Circle/shape/model candidates with score >= 0.40, and GENERAL only if no repository evidence reaches the threshold.
- References like "the code," "here," "this," "in here," "this project," "the repo," or "the codebase" MUST NOT be GENERAL.
- Architectural questions ("How does data flow?", "How is auth wired?", "How do modules interact?") are REPO_WIDE unless the user selected/named a concrete file or symbol.
- A selected graph file is strong evidence for SPECIFIC_CODE.

### EXAMPLES
- "Explain the code here" -> REPO_WIDE
- "What does the code do?" -> REPO_WIDE
- "How does this project handle auth?" -> REPO_WIDE
- "What is the main function of the repo?" + Memory candidate score 0.87 -> REPO_WIDE
- "Where is the database initialized?" + Memory candidate score 0.62 -> SPECIFIC_CODE
- "Look at the code in main.py and explain it" -> SPECIFIC_CODE
- "What is the purpose of the handle_request function?" -> SPECIFIC_CODE
- "How should I implement a Circle class?" + Memory candidate score 0.77 -> SPECIFIC_CODE
- "How should I implement a Circle class?" + no Memory candidate score >= 0.40 -> GENERAL
- "How do I write a for-loop in Python?" -> GENERAL

### OUTPUT RULES
- Return exactly one string: GENERAL, SPECIFIC_CODE, or REPO_WIDE.
- Do not explain. Do not use punctuation. Do not use quotes.
""".strip()

# Skip the remote classifier and always use the local keyword heuristic.
# Set to False to re-enable LLM-based classification when a paid API key is available.
_FORCE_LOCAL_CLASSIFICATION = True
# Kept for compatibility; unused while _FORCE_LOCAL_CLASSIFICATION is True.
CLASSIFICATION_TIMEOUT_SECONDS = 4.0

# Minimum Memory relevance score that makes a query specific-code.
SPECIFIC_CODE_SCORE_THRESHOLD = 0.40
# Keep classifier prompt evidence compact even when retrieval returns many snippets.
MAX_CANDIDATES_IN_CLASSIFIER_PROMPT = 10


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
async def classify_prompt(prompt: str, selected_file_path: str | None, classifier_model_name: str, retrieved_context: list[dict[str, Any]] | None = None) -> PromptClassificationResult:
    # Normalize optional retrieved context once.
    context_candidates = normalize_retrieved_context(retrieved_context)
    # When the local-only flag is set, skip the API call entirely.
    if _FORCE_LOCAL_CLASSIFICATION:
        classifier_category = classify_prompt_locally(prompt, selected_file_path, context_candidates)
        return build_result(classifier_category, classifier_model_name, "LOCAL_ONLY", True, "Remote classifier disabled.")
    # Build the strict OpenAI-compatible messages for classification.
    messages = build_classifier_messages(prompt, selected_file_path, context_candidates)
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
            classifier_category = classify_prompt_locally(prompt, selected_file_path, context_candidates)
            # Return fallback metadata.
            return build_result(classifier_category, classifier_model_name, raw_response, True, "LLM classifier returned an invalid category, so local fallback was used.")
        # Apply a deterministic repo-evidence guard when the model underuses Memory candidates.
        guarded_category = apply_context_bias(prompt, selected_file_path, context_candidates, classifier_category)
        # Return guard metadata when the LLM category was adjusted.
        if guarded_category != classifier_category:
            return build_result(guarded_category, classifier_model_name, raw_response, True, "Memory candidate evidence adjusted the classifier category.")
        # Return LLM classifier metadata.
        return build_result(classifier_category, classifier_model_name, raw_response, False, "Classified by the prompt classification LLM.")
    # Fall back locally when the classifier model is unavailable.
    except Exception as exc:
        # Choose a deterministic local category so the app can continue.
        classifier_category = classify_prompt_locally(prompt, selected_file_path, context_candidates)
        # Return fallback metadata without exposing credentials or provider internals.
        return build_result(classifier_category, classifier_model_name, f"LOCAL_FALLBACK: {exc.__class__.__name__}", True, "Classifier LLM failed, so local fallback was used.")


# Build the strict classifier messages.
def build_classifier_messages(prompt: str, selected_file_path: str | None, context_candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    # Build selected-file context for the classifier.
    selected_file_text = selected_file_path or "none"
    # Build compact Memory evidence for the classifier.
    memory_context_text = build_memory_context_text(context_candidates)
    # Build the user message with the prompt and graph selection.
    user_message = f"""
User prompt:
{prompt.strip()}

Selected graph file:
{selected_file_text}

Memory candidate files/snippets:
{memory_context_text}

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
def classify_prompt_locally(prompt: str, selected_file_path: str | None, retrieved_context: list[dict[str, Any]] | None = None) -> str:
    # Normalize optional retrieved context.
    context_candidates = normalize_retrieved_context(retrieved_context)
    # Keep greetings and conversational prompts general.
    if is_greeting_or_chat_prompt(prompt):
        return GENERAL
    # Route selected graph-file questions to specific-code context.
    if selected_file_path:
        # Return specific-code because the user selected a concrete file.
        return SPECIFIC_CODE
    # Respect explicit broad repo questions before applying Memory score.
    if has_repo_wide_cue(prompt) and not is_specific_code_prompt(prompt):
        return REPO_WIDE
    # Check whether Memory found a high-confidence candidate.
    has_specific_score = has_specific_score_match(context_candidates)
    # Use Memory matches unless the prompt is plainly asking for a generic definition.
    if not (is_general_theory_prompt(prompt) and not mentions_named_code_entity(prompt)):
        # Route high-scoring Memory matches to specific-code context.
        if has_specific_score:
            # Return specific-code because Memory found a high-confidence match.
            return SPECIFIC_CODE
    # Keep standalone implementation questions general when Memory found no repo match.
    if not has_specific_score and is_standalone_implementation_prompt(prompt):
        return GENERAL
    # Route file/symbol questions.
    if is_specific_code_prompt(prompt):
        # Return specific-code because the question points at code symbols or paths.
        return SPECIFIC_CODE
    # Default to general when no repo/code cues are present.
    return GENERAL


# Apply deterministic Memory evidence so a weak classifier cannot ignore focused repo matches.
def apply_context_bias(prompt: str, selected_file_path: str | None, context_candidates: list[dict[str, Any]], classifier_category: str) -> str:
    # Keep greetings and conversational prompts general.
    if is_greeting_or_chat_prompt(prompt):
        return GENERAL
    # Respect selected graph files as specific code context.
    if selected_file_path:
        return SPECIFIC_CODE
    # Repo-wide wording should not be overwritten by a high-scoring Memory candidate.
    if has_repo_wide_cue(prompt) and not is_specific_code_prompt(prompt):
        return REPO_WIDE
    # Check whether Memory found a high-confidence candidate.
    has_specific_score = has_specific_score_match(context_candidates)
    # Keep standalone implementation questions general when Memory found no repo match.
    if not has_specific_score and is_standalone_implementation_prompt(prompt):
        return GENERAL
    # No high-scoring Memory candidate means no score-based adjustment is needed.
    if not has_specific_score:
        return classifier_category
    # Avoid hijacking pure concept-definition questions.
    if is_general_theory_prompt(prompt) and not mentions_named_code_entity(prompt):
        return classifier_category
    # Any high-scoring Memory candidate means the question can be answered as specific code.
    return SPECIFIC_CODE


# Normalize retrieved context objects into the fields classification needs.
def normalize_retrieved_context(retrieved_context: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    # Return an empty list for missing or invalid context.
    if not isinstance(retrieved_context, list):
        return []
    # Prepare normalized candidates.
    normalized_candidates = []
    # Iterate over retrieved snippets.
    for item in retrieved_context:
        # Skip invalid entries.
        if not isinstance(item, dict):
            continue
        # Read common file path keys.
        file_path = str(item.get("file_path") or item.get("path") or item.get("filename") or "").strip()
        # Skip entries without a file path.
        if not file_path:
            continue
        # Store a compact candidate.
        normalized_candidates.append(
            {
                "file_path": file_path,
                "function_name": str(item.get("function_name") or item.get("name") or item.get("symbol") or "").strip(),
                "score": item.get("score"),
                "start_line": item.get("start_line"),
                "end_line": item.get("end_line"),
            }
        )
    # Return normalized candidates.
    return normalized_candidates


# Build compact Memory evidence text for the LLM classifier.
def build_memory_context_text(context_candidates: list[dict[str, Any]]) -> str:
    # Count unique files for display only.
    candidate_file_count = count_candidate_files(context_candidates)
    # Return a clear fallback when no Memory evidence exists.
    if candidate_file_count == 0:
        return "No Memory candidates were found."
    # Prepare top candidate lines.
    lines = [
        f"SPECIFIC_CODE score threshold: {SPECIFIC_CODE_SCORE_THRESHOLD}",
        f"Highest candidate score: {max_candidate_score(context_candidates)}",
        f"Unique candidate files: {candidate_file_count}",
    ]
    # Add a compact view of the first candidates only.
    for candidate in context_candidates[:MAX_CANDIDATES_IN_CLASSIFIER_PROMPT]:
        # Read the optional symbol name.
        symbol_text = f" :: {candidate['function_name']}" if candidate.get("function_name") else ""
        # Read optional line metadata.
        line_text = build_line_text(candidate)
        # Read optional score metadata.
        score_text = f" score={candidate['score']}" if candidate.get("score") is not None else ""
        # Add the candidate line.
        lines.append(f"- {candidate['file_path']}{symbol_text}{line_text}{score_text}")
    # Mention omitted candidates if retrieval returned more.
    if len(context_candidates) > MAX_CANDIDATES_IN_CLASSIFIER_PROMPT:
        lines.append(f"- ... {len(context_candidates) - MAX_CANDIDATES_IN_CLASSIFIER_PROMPT} more candidates omitted")
    # Return compact evidence.
    return "\n".join(lines)


# Count unique file paths in Memory candidates.
def count_candidate_files(context_candidates: list[dict[str, Any]]) -> int:
    # Return unique non-empty file path count.
    return len({candidate["file_path"] for candidate in context_candidates if candidate.get("file_path")})


# Decide whether any Memory candidate crosses the specific-code threshold.
def has_specific_score_match(context_candidates: list[dict[str, Any]]) -> bool:
    # Return true for the first high-confidence candidate.
    return any((score := parse_candidate_score(candidate.get("score"))) is not None and score >= SPECIFIC_CODE_SCORE_THRESHOLD for candidate in context_candidates)


# Return the highest numeric Memory score, if any.
def max_candidate_score(context_candidates: list[dict[str, Any]]) -> float | None:
    # Parse all numeric candidate scores.
    scores = [score for candidate in context_candidates if (score := parse_candidate_score(candidate.get("score"))) is not None]
    # Return no score when none are usable.
    if not scores:
        return None
    # Return a compact score for prompt readability.
    return round(max(scores), 4)


# Parse a Memory score into a float.
def parse_candidate_score(score: Any) -> float | None:
    # Keep missing scores from affecting threshold decisions.
    if score is None:
        return None
    # Convert numeric or numeric-string scores.
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


# Build optional line range text for a Memory candidate.
def build_line_text(candidate: dict[str, Any]) -> str:
    # Read start and end line values.
    start_line = candidate.get("start_line")
    end_line = candidate.get("end_line")
    # Return no line text when either side is missing.
    if start_line is None or end_line is None:
        return ""
    # Return a compact line label.
    return f" lines={start_line}-{end_line}"


# Detect explicit code/file/symbol prompts.
def is_specific_code_prompt(prompt: str) -> bool:
    # File paths/extensions are specific code evidence.
    if re.search(r"[\w./-]+\.(py|js|jsx|ts|tsx|java|go|rb|php|cpp|c|h|hpp)\b", prompt, re.IGNORECASE):
        return True
    # Routes and endpoints are specific code evidence.
    if re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/", prompt):
        return True
    # Named implementation entities are specific code evidence.
    if mentions_named_code_entity(prompt):
        return True
    # Location questions usually expect focused code files.
    return bool(re.search(r"\b(where is|which file|specific file|handler|endpoint|route|import)\b", prompt, re.IGNORECASE))


# Detect repo-wide wording.
def has_repo_wide_cue(prompt: str) -> bool:
    # Normalize prompt text.
    lowered = prompt.lower()
    # Match wording that explicitly asks about the loaded codebase.
    return any(
        term in lowered
        for term in (
            "repo",
            "repository",
            "architecture",
            "data flow",
            "dependencies",
            "all files",
            "whole code",
            "whole project",
            "entire project",
            "overall",
            "overview",
            "summary",
            "codebase",
            "this project",
            "the code",
            "code here",
            "refactor",
            "rewrite",
            "debug this",
            "bug in",
            "where should",
            "how do i add",
            "how should i add",
            "where do i implement",
            "where should i implement",
        )
    )


# Detect implementation questions that are general unless Memory/repo wording anchors them.
def is_standalone_implementation_prompt(prompt: str) -> bool:
    # Repo wording means the implementation question belongs to the codebase.
    if has_repo_wide_cue(prompt):
        return False
    # Explicit files or routes are not standalone.
    if re.search(r"[\w./-]+\.(py|js|jsx|ts|tsx|java|go|rb|php|cpp|c|h|hpp)\b", prompt, re.IGNORECASE):
        return False
    if re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/", prompt):
        return False
    # Match common standalone implementation asks.
    return bool(re.search(r"\b(how\s+(do|should|can)\s+i\s+|how\s+to\s+|can\s+you\s+)?(implement|create|build|write|make|add)\b", prompt, re.IGNORECASE))


# Detect named symbols/classes/functions rather than generic theory terms.
def mentions_named_code_entity(prompt: str) -> bool:
    # Match capitalized, camelCase, snake_case, or dotted symbols near code entity words.
    return bool(
        re.search(
            r"\b([A-Z][A-Za-z0-9_]*|[a-z]+[A-Z][A-Za-z0-9_]*|[a-z_]+_[a-z0-9_]+)\s+(class|function|method|component|service|handler|endpoint|route)\b",
            prompt,
        )
        or re.search(
            r"\b(class|function|method|component|service|handler|endpoint|route)\s+([A-Z][A-Za-z0-9_]*|[a-z]+[A-Z][A-Za-z0-9_]*|[a-z_]+_[a-z0-9_]+)\b",
            prompt,
        )
    )


# Detect pure concept-definition prompts that should remain general without named repo evidence.
def is_general_theory_prompt(prompt: str) -> bool:
    # Match common educational concept questions.
    return bool(re.search(r"^\s*(what is|what are|explain|define)\s+(a|an|the)?\s*(class|function|method|interface|api|object|variable|loop|inheritance|polymorphism)\b", prompt, re.IGNORECASE))


# Detect simple conversational prompts that should not be pulled into repo context.
def is_greeting_or_chat_prompt(prompt: str) -> bool:
    # Normalize lightweight conversational text.
    normalized = prompt.strip().lower()
    # Match short greetings or assistant-directed chat.
    return normalized in {"hi", "hello", "hey", "thanks", "thank you"} or bool(re.search(r"^\s*(hi|hello|hey)\b", prompt, re.IGNORECASE))


# Build the frontend response object.
def build_result(classifier_category: str, classifier_model_name: str, raw_response: str, used_local_fallback: bool, reason: str) -> PromptClassificationResult:
    # Return the structured result.
    return PromptClassificationResult(category=FRONTEND_CATEGORY_VALUES[classifier_category], label=CATEGORY_LABELS[classifier_category], classifier_category=classifier_category, classifier_model=classifier_model_name, raw_classifier_response=raw_response, used_local_fallback=used_local_fallback, reason=reason)
