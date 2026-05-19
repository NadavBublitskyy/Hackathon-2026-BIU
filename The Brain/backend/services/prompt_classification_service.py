"""This file owns LLM-based prompt category classification for frontend routing."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from backend.config import get_settings
from backend.llm_client import get_llm_connector
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError
from backend.services.memory_retrieval_service import calculate_query_relevance_score, calculate_semantic_canary_match, tokenize_terms
from backend.services.repo_session_store import load_code_chunks_json, load_repo_identity

GENERAL = "GENERAL"
SPECIFIC_CODE = "SPECIFIC_CODE"
REPO_WIDE = "REPO_WIDE"

CATEGORY_LABELS = {
    GENERAL: "General",
    SPECIFIC_CODE: "Specific code",
    REPO_WIDE: "Repo-wide",
}

FRONTEND_CATEGORY_VALUES = {
    GENERAL: "general",
    SPECIFIC_CODE: "specific_code",
    REPO_WIDE: "repo_wide",
}

PROMPT_CLASSIFIER_SYSTEM_PROMPT = """
You are a high-precision routing classifier for a repository explorer.
Choose the one route that should handle the user's next message.

Routes:
GENERAL: The answer does not need the loaded repository. Use this for normal conversation and general programming explanations.
SPECIFIC_CODE: The answer should focus on a concrete file, selected graph file, named class/function/method/component/service/route, explicit path, or a "where is / which file" lookup. 
REPO_WIDE: The answer needs broad repository context, architecture, entire code flow, overall behavior, cross-file interactions, dependency relationships, or how a feature is wired through the project. In addition, it should include any refrence to the code that is general phrased such as what is the code flow here? is this code good? what is the program flow etc

Decision rules:
- If the selected graph file is not "none", use SPECIFIC_CODE unless the prompt explicitly asks about the whole project, full architecture, overall behavior, or entire code flow.
- Use the current repository identity and context matcher as routing evidence.
- If the user query relates to the repository's tech stack, core keywords, README summary, or matched repo identity keywords, choose REPO_WIDE unless the user selected or named one concrete file/symbol.
- If the user query is a generic programming question that does not relate to the repository identity, choose GENERAL even when a repository is loaded.
- Questions like "what is the entire code flow?", "what does this project do?", "explain the codebase", "how does data flow?", and "show the architecture" are REPO_WIDE.
- Do not choose SPECIFIC_CODE merely because the repository is loaded.
- Do not infer an attached file unless a selected graph file is provided or the prompt names a concrete file/symbol.
- Return exactly one string: GENERAL, SPECIFIC_CODE, or REPO_WIDE.
- Do not explain. Do not use punctuation. Do not use quotes.
""".strip()

CLASSIFICATION_TIMEOUT_SECONDS = 8.0
SEMANTIC_CANARY_OVERRIDE_THRESHOLD = 0.70
IDENTITY_MATCH_CANARY_THRESHOLD = 0.40

REPO_REFERENCE_PATTERNS = (
    r"\brepo\b",
    r"\brepository\b",
    r"\bproject\b",
    r"\bcodebase\b",
    r"\bcode base\b",
    r"\bthis\s+(code|repo|repository|project|app|application|codebase)\b",
    r"\bcurrent\s+(code|repo|repository|project|app|application|codebase)\b",
    r"\bloaded\s+(code|repo|repository|project|app|application|codebase)\b",
    r"\bin\s+here\b",
)

GENERIC_LANGUAGE_HOWTO_PATTERN = re.compile(
    r"\bhow\s+(?:do|can|should|would)?\s*i?\s*(?:write|implement|create|make|build|define)\b.*\b(function|method|class|algorithm|program|script)\b"
    r"|\b(function|method|class|algorithm|program|script)\b.*\b(?:in|using|with)\s+(python|java|javascript|typescript|go|rust|ruby|php|swift|kotlin|c\+\+|c#)\b",
    re.IGNORECASE,
)

GENERIC_REPO_OVERRIDE_TERMS = {
    "algorithm",
    "build",
    "class",
    "code",
    "create",
    "define",
    "function",
    "implement",
    "java",
    "javascript",
    "kotlin",
    "method",
    "program",
    "python",
    "return",
    "returns",
    "ruby",
    "rust",
    "script",
    "swift",
    "typescript",
    "using",
    "write",
}
MIN_DISTINCTIVE_REPO_TERM_HITS = 2
WHOLE_REPO_PROMPT_PATTERN = re.compile(
    r"\b(whole|entire|overall|architecture|codebase|code\s+base|project|repository|repo|data\s+flow|code\s+flow)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RepoMatchSignals:
    canary_score: float = 0.0
    canary_file_path: str | None = None
    canary_function_name: str | None = None
    topic_keywords: tuple[str, ...] = ()
    topic_match_keywords: tuple[str, ...] = ()
    identity_sentence: str = ""


@dataclass(frozen=True)
class PromptClassificationResult:
    category: str
    label: str
    classifier_category: str
    classifier_model: str
    raw_classifier_response: str
    used_local_fallback: bool
    reason: str
    repo_relevance_score: float | None = None
    canary_score: float | None = None
    canary_file_path: str | None = None
    topic_keywords: tuple[str, ...] = ()
    topic_match_keywords: tuple[str, ...] = ()


async def classify_prompt(
    prompt: str,
    selected_file_path: str | None,
    classifier_model_name: str,
    retrieved_context: list[dict] | None = None,
    repo_session_id: str | None = None,
) -> PromptClassificationResult:
    """Classify a prompt by making a real LLM request."""
    # Keep the request schema backward-compatible, but do not let retrieved snippets bias routing.
    del retrieved_context

    if selected_file_path and not asks_for_whole_repo(prompt):
        return build_result(
            classifier_category=SPECIFIC_CODE,
            classifier_model_name=classifier_model_name,
            raw_response="SELECTED_FILE_RULE",
            reason="Selected graph file is active, so the prompt is routed to that file's code chunks only.",
        )

    repo_identity = load_repo_identity_for_classification(repo_session_id)
    topic_keywords = extract_prompt_topics(prompt)
    topic_match_keywords = match_topics_to_repo_identity(topic_keywords, repo_identity)
    messages = build_classifier_messages(prompt, selected_file_path, repo_identity, topic_keywords, topic_match_keywords)

    classifier_task = send_classifier_request(messages, classifier_model_name)
    signals_task = asyncio.to_thread(calculate_repo_match_signals, prompt, repo_session_id, repo_identity, topic_keywords, topic_match_keywords)
    (result, classifier_fallback_used), repo_signals = await asyncio.gather(classifier_task, signals_task)

    raw_response = result.message.strip()
    classifier_category = parse_classifier_category(raw_response)

    if classifier_category is None:
        preview = raw_response[:120] if raw_response else "<empty>"
        raise LLMError(f"Prompt classifier returned an invalid route: {preview}")

    if should_override_general_to_repo_wide(prompt, selected_file_path, repo_signals, classifier_category):
        return build_result(
            classifier_category=REPO_WIDE,
            classifier_model_name=result.model or classifier_model_name,
            raw_response=raw_response,
            reason=build_reason(
                classifier_fallback_used,
                classifier_model_name,
                result.model or classifier_model_name,
                build_repo_override_reason(repo_signals),
            ),
            repo_signals=repo_signals,
        )

    return build_result(
        classifier_category=classifier_category,
        classifier_model_name=result.model or classifier_model_name,
        raw_response=raw_response,
        reason=build_reason(classifier_fallback_used, classifier_model_name, result.model or classifier_model_name, "Classified by the prompt classification LLM."),
        repo_signals=repo_signals,
    )


def build_classifier_messages(
    prompt: str,
    selected_file_path: str | None,
    repo_identity: dict,
    topic_keywords: tuple[str, ...],
    topic_match_keywords: tuple[str, ...],
) -> list[dict[str, str]]:
    selected_file_text = selected_file_path or "none"
    identity_text = format_repo_identity_for_prompt(repo_identity)
    topic_text = ", ".join(topic_keywords) if topic_keywords else "none"
    match_text = ", ".join(topic_match_keywords) if topic_match_keywords else "none"
    user_message = f"""
Current repository identity:
{identity_text}

Topic extractor keywords:
{topic_text}

Context matcher result:
Matched repo identity keywords: {match_text}
Match count: {len(topic_match_keywords)}

User prompt:
{prompt.strip()}

Selected graph file:
{selected_file_text}

Return exactly one route:
GENERAL
SPECIFIC_CODE
REPO_WIDE
""".strip()

    return [
        {"role": "system", "content": PROMPT_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def parse_classifier_category(response: str) -> str | None:
    if not response.strip():
        return None

    first_line = response.strip().splitlines()[0]
    normalized = normalize_category_text(first_line)

    if normalized in {GENERAL, SPECIFIC_CODE, REPO_WIDE}:
        return normalized

    whole_response = normalize_category_text(response)
    matches = [category for category in (GENERAL, SPECIFIC_CODE, REPO_WIDE) if category in whole_response]

    if len(matches) == 1:
        return matches[0]

    return None


def normalize_category_text(value: str) -> str:
    cleaned = value.strip().strip("\"'`.,;:")
    cleaned = re.sub(r"[^A-Za-z_-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_").upper().replace("-", "_")


async def send_classifier_request(messages: list[dict[str, str]], classifier_model_name: str):
    try:
        result = await asyncio.wait_for(
            get_llm_connector().send_messages(
                messages=messages,
                temperature=0.0,
                max_tokens=12,
                model_name=classifier_model_name,
            ),
            timeout=CLASSIFICATION_TIMEOUT_SECONDS,
        )
        return result, False
    except asyncio.TimeoutError as exc:
        raise LLMError("Prompt classifier timed out before returning a route.") from exc
    except (LLMAuthError, LLMConfigError):
        raise
    except LLMError:
        fallback_model_name = get_settings().llm_model_name
        if not fallback_model_name or fallback_model_name == classifier_model_name:
            raise

    try:
        result = await asyncio.wait_for(
            get_llm_connector().send_messages(
                messages=messages,
                temperature=0.0,
                max_tokens=12,
                model_name=fallback_model_name,
            ),
            timeout=CLASSIFICATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise LLMError("Prompt classifier fallback timed out before returning a route.") from exc

    return result, True


def build_reason(classifier_fallback_used: bool, requested_model_name: str, actual_model_name: str, base_reason: str) -> str:
    if classifier_fallback_used:
        return f"Classifier model {requested_model_name} failed; retried with {actual_model_name}. {base_reason}"

    return base_reason


def build_result(
    classifier_category: str,
    classifier_model_name: str,
    raw_response: str,
    reason: str,
    repo_signals: RepoMatchSignals | None = None,
) -> PromptClassificationResult:
    signals = repo_signals or RepoMatchSignals()
    return PromptClassificationResult(
        category=FRONTEND_CATEGORY_VALUES[classifier_category],
        label=CATEGORY_LABELS[classifier_category],
        classifier_category=classifier_category,
        classifier_model=classifier_model_name,
        raw_classifier_response=raw_response,
        used_local_fallback=False,
        reason=reason,
        repo_relevance_score=signals.canary_score,
        canary_score=signals.canary_score,
        canary_file_path=signals.canary_file_path,
        topic_keywords=signals.topic_keywords,
        topic_match_keywords=signals.topic_match_keywords,
    )


def calculate_repo_relevance_score(prompt: str, repo_session_id: str | None) -> float:
    if not repo_session_id:
        return 0.0

    try:
        code_chunks_json = load_code_chunks_json(repo_session_id)
    except (FileNotFoundError, ValueError):
        return 0.0

    return calculate_query_relevance_score(prompt, code_chunks_json)


def should_override_general_to_repo_wide(
    prompt: str,
    selected_file_path: str | None,
    repo_signals: RepoMatchSignals,
    classifier_category: str,
) -> bool:
    if classifier_category != GENERAL:
        return False
    if selected_file_path:
        return False

    if is_generic_language_howto(prompt):
        return False

    if repo_signals.canary_score > SEMANTIC_CANARY_OVERRIDE_THRESHOLD:
        return True

    if repo_signals.topic_match_keywords and repo_signals.canary_score >= IDENTITY_MATCH_CANARY_THRESHOLD:
        return True

    return False


def build_repo_override_reason(repo_signals: RepoMatchSignals) -> str:
    if repo_signals.canary_score > SEMANTIC_CANARY_OVERRIDE_THRESHOLD:
        return f"LLM classified GENERAL, but the Chroma canary match crossed {SEMANTIC_CANARY_OVERRIDE_THRESHOLD:.2f} with score {repo_signals.canary_score:.4f}."

    matched_topics = ", ".join(repo_signals.topic_match_keywords) or "none"
    return (
        "LLM classified GENERAL, but the topic matcher found repo identity keywords "
        f"({matched_topics}) and the Chroma canary score {repo_signals.canary_score:.4f} crossed {IDENTITY_MATCH_CANARY_THRESHOLD:.2f}."
    )


def load_repo_identity_for_classification(repo_session_id: str | None) -> dict:
    if not repo_session_id:
        return {}

    try:
        return load_repo_identity(repo_session_id)
    except (FileNotFoundError, ValueError):
        return {}


def calculate_repo_match_signals(
    prompt: str,
    repo_session_id: str | None,
    repo_identity: dict,
    topic_keywords: tuple[str, ...],
    topic_match_keywords: tuple[str, ...],
) -> RepoMatchSignals:
    canary_match = {"score": 0.0, "file_path": None, "function_name": None}

    if repo_session_id:
        try:
            code_chunks_json = load_code_chunks_json(repo_session_id)
        except (FileNotFoundError, ValueError):
            code_chunks_json = []

        if code_chunks_json:
            canary_match = calculate_semantic_canary_match(prompt, code_chunks_json)

    return RepoMatchSignals(
        canary_score=float(canary_match.get("score") or 0.0),
        canary_file_path=canary_match.get("file_path"),
        canary_function_name=canary_match.get("function_name"),
        topic_keywords=topic_keywords,
        topic_match_keywords=topic_match_keywords,
        identity_sentence=str(repo_identity.get("identity_sentence") or ""),
    )


def extract_prompt_topics(prompt: str) -> tuple[str, ...]:
    seen: set[str] = set()
    topics: list[str] = []

    for term in tokenize_terms(prompt):
        if term in GENERIC_REPO_OVERRIDE_TERMS or term in seen:
            continue
        seen.add(term)
        topics.append(term)

    return tuple(topics[:12])


def match_topics_to_repo_identity(topic_keywords: tuple[str, ...], repo_identity: dict) -> tuple[str, ...]:
    if not topic_keywords or not isinstance(repo_identity, dict):
        return ()

    identity_terms: set[str] = set()
    for key in ("project_name", "readme_summary", "identity_sentence"):
        identity_terms.update(tokenize_terms(str(repo_identity.get(key) or "")))

    for value in repo_identity.get("tech_stack") or []:
        identity_terms.update(tokenize_terms(str(value)))
    for value in repo_identity.get("core_keywords") or []:
        identity_terms.update(tokenize_terms(str(value)))

    return tuple(term for term in topic_keywords if term in identity_terms)


def format_repo_identity_for_prompt(repo_identity: dict) -> str:
    if not repo_identity:
        return "No repository identity card is available."

    project_name = repo_identity.get("project_name") or "unknown"
    tech_stack = ", ".join(str(value) for value in repo_identity.get("tech_stack") or []) or "unknown"
    core_keywords = ", ".join(str(value) for value in repo_identity.get("core_keywords") or []) or "none"
    readme_summary = repo_identity.get("readme_summary") or "No README summary was available."

    return "\n".join(
        [
            f"Project: {project_name}",
            f"Tech stack: {tech_stack}",
            f"Core keywords: {core_keywords}",
            f"README summary: {readme_summary}",
        ]
    )


def has_explicit_repo_reference(prompt: str) -> bool:
    normalized = prompt.lower()
    return any(re.search(pattern, normalized) for pattern in REPO_REFERENCE_PATTERNS)


def is_generic_language_howto(prompt: str) -> bool:
    return bool(GENERIC_LANGUAGE_HOWTO_PATTERN.search(prompt))


def asks_for_whole_repo(prompt: str) -> bool:
    return bool(WHOLE_REPO_PROMPT_PATTERN.search(prompt))


def count_distinctive_repo_term_hits(prompt: str, repo_session_id: str | None) -> int:
    if not repo_session_id:
        return 0

    query_terms = set(tokenize_terms(prompt)) - GENERIC_REPO_OVERRIDE_TERMS
    if not query_terms:
        return 0

    try:
        code_chunks_json = load_code_chunks_json(repo_session_id)
    except (FileNotFoundError, ValueError):
        return 0

    repo_terms: set[str] = set()
    for chunk in code_chunks_json:
        if not isinstance(chunk, dict):
            continue
        searchable_text = " ".join(
            str(chunk.get(key) or "")
            for key in ("file_path", "path", "name", "entity_name", "function_name", "scope", "type", "content")
        )
        repo_terms.update(tokenize_terms(searchable_text))

    return len(query_terms & repo_terms)
