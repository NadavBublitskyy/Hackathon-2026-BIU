"""This file defines the LLM exception types shared by routes and services."""


# Define the base exception type for LLM-related failures.
class LLMError(Exception):
    # Keep the base error class intentionally empty because its type is what matters.
    pass


# Define the exception type for missing or invalid local configuration.
class LLMConfigError(LLMError):
    # Keep this class empty so callers can catch configuration failures specifically.
    pass


# Define the exception type for provider authentication failures.
class LLMAuthError(LLMError):
    # Keep this class empty so callers can translate auth failures into HTTP 401.
    pass


# Define the exception type for provider rate-limit responses (HTTP 429).
# A 429 proves the key is valid — the provider just needs time to recover.
class LLMRateLimitError(LLMError):
    pass
