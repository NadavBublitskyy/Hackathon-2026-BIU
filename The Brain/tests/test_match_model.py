"""Tests for dynamic model routing and per-request model selection."""

# Import asyncio so fake connector calls can simulate slow classifier responses.
import asyncio
# Import sys so the backend package can be imported from the Brain folder.
import sys
# Import unittest for the project's existing test style.
import unittest
# Import SimpleNamespace so fake LLM results can expose message and raw attributes.
from types import SimpleNamespace
# Import Path so the Brain directory can be added to sys.path.
from pathlib import Path


# Resolve the Brain directory that contains the backend package.
BRAIN_DIR = Path(__file__).resolve().parents[1]
# Add the Brain directory to Python imports for direct unittest execution.
sys.path.insert(0, str(BRAIN_DIR))

# Import the model router under test.
from backend.match_model import DEFAULT_CLASSIFIER_MODEL_NAME, MatchModel  # noqa: E402


# Try to import the real connector so the payload override can be tested when dependencies are installed.
try:
    # Import the connector class after sys.path is configured.
    from backend.setup import LLMConnector  # noqa: E402
# Skip connector-specific tests when local FastAPI/httpx dependencies are not installed.
except ModuleNotFoundError:
    # Store None so unittest can skip the connector test class.
    LLMConnector = None


# Define a fake LLM connector for deterministic MatchModel tests.
class FakeConnector:
    # Initialize the fake connector with a classifier response and optional delay.
    def __init__(self, message: str, delay_seconds: float = 0.0):
        # Store the text that should be returned by send_messages.
        self.message = message
        # Store an artificial delay for timeout tests.
        self.delay_seconds = delay_seconds
        # Record every request made by MatchModel.
        self.calls: list[dict[str, object]] = []

    # Simulate the connector method used by MatchModel.
    async def send_messages(self, messages, temperature=0.2, max_tokens=800, model_name=None):
        # Record the request so tests can inspect the model and payload.
        self.calls.append({"messages": messages, "temperature": temperature, "max_tokens": max_tokens, "model_name": model_name})
        # Sleep when the test wants to force a classifier timeout.
        if self.delay_seconds:
            # Yield control back to the event loop for the requested delay.
            await asyncio.sleep(self.delay_seconds)
        # Return a minimal object that looks like LLMResult.
        return SimpleNamespace(message=self.message, raw={}, model=model_name)


# Define fake settings with only the attributes LLMConnector needs.
class FakeSettings:
    # Store the provider base URL used by the real connector constructor.
    llm_base_url = "https://example.test/api/v1"
    # Store the total request timeout used by the real connector constructor.
    llm_request_timeout_seconds = 30.0
    # Store the connect timeout used by the real connector constructor.
    llm_connect_timeout_seconds = 5.0
    # Store the app name used by provider headers.
    app_name = "Router Tests"
    # Store the default configured model.
    llm_model_name = "default-model"
    # Store retry count so the connector does not retry in this unit test.
    llm_max_retries = 0
    # Store the fake key value used by provider headers.
    api_key_value = "test-key"


# Define a fake HTTP response for connector payload tests.
class FakeResponse:
    # Initialize a successful OpenAI-compatible response.
    def __init__(self):
        # Store HTTP 200 so the connector treats the response as successful.
        self.status_code = 200
        # Store empty text for fallback error formatting.
        self.text = ""

    # Return the provider JSON body expected by LLMConnector.
    def json(self):
        # Return a single assistant message.
        return {"choices": [{"message": {"content": "ok"}}]}


# Define a fake async HTTP client that records request payloads.
class FakeHTTPClient:
    # Initialize the request log.
    def __init__(self):
        # Store every request made by LLMConnector.
        self.requests: list[dict[str, object]] = []

    # Simulate httpx.AsyncClient.request.
    async def request(self, method, path, **kwargs):
        # Record the outbound request for assertions.
        self.requests.append({"method": method, "path": path, **kwargs})
        # Return a successful fake response.
        return FakeResponse()


# Test MatchModel with a fake LLM classifier.
class MatchModelTests(unittest.IsolatedAsyncioTestCase):
    # Verify a navigation question can route to the light model.
    async def test_navigation_prompt_routes_to_light_model(self):
        # Define the caller-provided light model.
        light_model = "cheap/light-model"
        # Define the caller-provided heavy model.
        heavy_model = "smart/heavy-model"
        # Create a fake connector whose classifier answer is exactly the light model.
        connector = FakeConnector(light_model)
        # Create the router with the fake connector.
        router = MatchModel(connector)
        # Route a simple file lookup question.
        result = await router.choose_model("Where is the getName function?", light_model, heavy_model)
        # Assert the selected model is the light model.
        self.assertEqual(result.selected_model, light_model)
        # Assert the difficulty metadata is easy.
        self.assertEqual(result.difficulty, "EASY")
        # Assert the cheap classifier model was used for classification.
        self.assertEqual(connector.calls[0]["model_name"], DEFAULT_CLASSIFIER_MODEL_NAME)
        # Assert the classifier request is deterministic.
        self.assertEqual(connector.calls[0]["temperature"], 0.0)

    # Verify a rewrite question can route to the heavy model.
    async def test_rewrite_prompt_routes_to_heavy_model(self):
        # Define the caller-provided light model.
        light_model = "cheap/light-model"
        # Define the caller-provided heavy model.
        heavy_model = "smart/heavy-model"
        # Create a fake connector whose classifier answer is exactly the heavy model.
        connector = FakeConnector(heavy_model)
        # Create the router with the fake connector.
        router = MatchModel(connector, classifier_model_name="openai/gpt-4o-mini")
        # Route a hard rewrite request.
        result = await router.choose_model("How do I rewrite this auth flow safely?", light_model, heavy_model)
        # Assert the selected model is the heavy model.
        self.assertEqual(result.selected_model, heavy_model)
        # Assert the difficulty metadata is hard.
        self.assertEqual(result.difficulty, "HARD")

    # Verify the classifier prompt exposes only two valid output choices.
    def test_classifier_prompt_forces_exact_model_options(self):
        # Build the messages sent to the cheap classifier.
        messages = MatchModel.build_classifier_messages("Find the database file.", "cheap/light-model", "smart/heavy-model")
        # Read the system message.
        system_message = messages[0]["content"]
        # Read the user message.
        user_message = messages[1]["content"]
        # Assert the system message forbids explanations.
        self.assertIn("Do not explain", system_message)
        # Assert the prompt asks for exactly one string.
        self.assertIn("Return exactly one of these two strings", user_message)
        # Assert the light model is one of the only options shown.
        self.assertIn("cheap/light-model", user_message)
        # Assert the heavy model is one of the only options shown.
        self.assertIn("smart/heavy-model", user_message)

    # Verify local fallback handles non-compliant classifier text.
    async def test_invalid_classifier_response_falls_back_to_local_keywords(self):
        # Define the caller-provided light model.
        light_model = "cheap/light-model"
        # Define the caller-provided heavy model.
        heavy_model = "smart/heavy-model"
        # Create a fake connector that returns an invalid classifier answer.
        connector = FakeConnector("This is probably hard.")
        # Create the router with the fake connector.
        router = MatchModel(connector)
        # Route a hard prompt that the local fallback can recognize.
        result = await router.choose_model("How should I refactor the payment logic?", light_model, heavy_model)
        # Assert the fallback selected the heavy model.
        self.assertEqual(result.selected_model, heavy_model)
        # Assert the result records fallback usage.
        self.assertTrue(result.used_local_fallback)

    # Verify the classification timeout keeps overhead under the required budget.
    async def test_classifier_timeout_keeps_routing_under_500ms(self):
        # Define the caller-provided light model.
        light_model = "cheap/light-model"
        # Define the caller-provided heavy model.
        heavy_model = "smart/heavy-model"
        # Create a fake connector that is slower than the router timeout.
        connector = FakeConnector(light_model, delay_seconds=1.0)
        # Create the router with a tiny timeout to keep the test fast.
        router = MatchModel(connector, classification_timeout_seconds=0.01)
        # Route a simple navigation prompt.
        result = await router.choose_model("Where is the DB logic?", light_model, heavy_model)
        # Assert the local fallback still chooses the light model.
        self.assertEqual(result.selected_model, light_model)
        # Assert the timeout fallback was recorded.
        self.assertTrue(result.used_local_fallback)
        # Assert the measured classification overhead is below the acceptance threshold.
        self.assertLess(result.classification_ms, 500)

    # Verify the convenience method returns only the selected model string.
    async def test_match_model_returns_plain_model_string(self):
        # Define the caller-provided light model.
        light_model = "cheap/light-model"
        # Define the caller-provided heavy model.
        heavy_model = "smart/heavy-model"
        # Create a fake connector whose classifier answer is the light model.
        connector = FakeConnector(light_model)
        # Create the router with the fake connector.
        router = MatchModel(connector)
        # Use the simple API requested by the user.
        selected_model = await router.match_model("Which file contains verify_token?", light_model, heavy_model)
        # Assert only the model string is returned.
        self.assertEqual(selected_model, light_model)


# Test that the real connector places the selected model into the provider payload.
@unittest.skipIf(LLMConnector is None, "backend.setup dependencies are not installed")
class LLMConnectorModelOverrideTests(unittest.IsolatedAsyncioTestCase):
    # Verify send_messages uses the per-request model override.
    async def test_send_messages_uses_model_override_in_payload(self):
        # Create the real connector with fake settings.
        connector = LLMConnector(FakeSettings())
        # Replace the real HTTP client with a recording fake client.
        fake_client = FakeHTTPClient()
        # Store the fake client on the connector.
        connector._client = fake_client
        # Send a request with an explicit routed model name.
        result = await connector.send_messages(messages=[{"role": "user", "content": "hello"}], model_name="smart/heavy-model")
        # Read the JSON payload sent to the provider.
        payload = fake_client.requests[0]["json"]
        # Assert the provider payload used the selected model instead of the default.
        self.assertEqual(payload["model"], "smart/heavy-model")
        # Assert the result metadata records the selected model.
        self.assertEqual(result.model, "smart/heavy-model")


# Allow direct execution with python -m unittest.
if __name__ == "__main__":
    # Run the tests in this file.
    unittest.main()
