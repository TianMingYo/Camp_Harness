import json

import httpx
import pytest

from feedbackloop.context import AgentContext
from feedbackloop.llm import (
    InvalidLLMResponse,
    LLMProviderError,
    LLMResponse,
    MockLLM,
    OpenAICompatibleClient,
    parse_action_response,
)
from feedbackloop.models import ActionType


class Credentials:
    def get(self, provider: str) -> str | None:
        return "test-key" if provider == "demo" else None


def context() -> AgentContext:
    return AgentContext(task_request="add greeting", plan_summary="edit app", recent_iterations=(), files=())


def test_parser_rejects_unknown_action_type():
    with pytest.raises(InvalidLLMResponse):
        parse_action_response('{"actions":[{"type":"invent","path_or_command":"x"}]}')


def test_parser_builds_typed_actions():
    response = parse_action_response(
        json.dumps({"actions": [{"type": "write", "path_or_command": "app.py", "content": "ok"}]})
    )
    assert response[0].type is ActionType.WRITE


def test_mock_llm_returns_responses_in_order():
    first = LLMResponse(actions=())
    second = LLMResponse(actions=())
    mock = MockLLM([first, second])
    assert mock.complete(context()) is first
    assert mock.complete(context()) is second
    with pytest.raises(LLMProviderError):
        mock.complete(context())


def test_openai_compatible_client_uses_chat_completions_and_bearer_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"actions":[{"type":"read","path_or_command":"README.md"}]}'}}]},
        )

    client = OpenAICompatibleClient(
        base_url="https://provider.test/v1",
        model="glm-5.2",
        provider="demo",
        credential_provider=Credentials(),
        transport=httpx.MockTransport(handler),
    )
    response = client.complete(context())
    assert response.actions[0].type is ActionType.READ


def test_provider_errors_are_typed():
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable"))
    client = OpenAICompatibleClient(
        base_url="https://provider.test/v1", model="m", provider="demo",
        credential_provider=Credentials(), transport=transport,
    )
    with pytest.raises(LLMProviderError):
        client.complete(context())
