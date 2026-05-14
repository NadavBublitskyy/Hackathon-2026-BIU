"""Compatibility wrapper for dynamic model routing."""

# Re-export the orchestrator implementation so older imports continue to work.
from backend.orchestrator.match_model import *  # noqa: F401,F403
