"""Compatibility wrapper for context-aware prompt construction."""

# Re-export the orchestrator implementation so older imports continue to work.
from backend.orchestrator.llm_blueprint import *  # noqa: F401,F403
