"""Compatibility wrapper for LLM setup imports."""

# Re-export configuration helpers so older imports continue to work.
from backend.config import Settings, get_settings  # noqa: F401
# Re-export the remote client and singleton lifecycle helpers.
from backend.llm_client import LLMConnector, LLMResult, LLMStatus, close_llm_connection, get_llm_connector, get_llm_status, setup_llm_connection  # noqa: F401
# Re-export LLM exceptions from the dedicated error module.
from backend.llm_errors import LLMAuthError, LLMConfigError, LLMError  # noqa: F401
