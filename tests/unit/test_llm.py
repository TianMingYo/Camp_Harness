import json

import httpx
import pytest

import feedbackloop.llm as llm
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


def test_plan_parser_requires_complete_structured_plan():
    payload = json.dumps(
        {
            "summary": "Add a greeting endpoint",
            "files": ["src/app.py", "tests/test_app.py"],
            "steps": ["Add the endpoint", "Cover it with a test"],
            "expected_behavior": "GET /greeting returns 200 and a greeting",
            "acceptance_criteria": ["The focused test passes"],
            "validation_commands": ["python -m pytest tests/test_app.py"],
            "potential_dangerous_actions": [],
            "estimated_iterations": 2,
        }
    )

    plan = llm.parse_plan_response(payload)

    assert plan.files == ("src/app.py", "tests/test_app.py")
    assert plan.expected_behavior == "GET /greeting returns 200 and a greeting"
    assert plan.validation_commands == ("python -m pytest tests/test_app.py",)
    assert plan.estimated_iterations == 2

    incomplete = json.loads(payload)
    del incomplete["expected_behavior"]
    with pytest.raises(InvalidLLMResponse):
        llm.parse_plan_response(json.dumps(incomplete))


def test_invalid_plan_response_retains_raw_content_for_boundary_redaction():
    raw = '{"api_key":"sk-private-value","unexpected":true}'

    with pytest.raises(InvalidLLMResponse) as caught:
        llm.parse_plan_response(raw)

    assert caught.value.raw_content == raw


@pytest.mark.parametrize("dangerous_action", ["format_disk", "write"])
def test_plan_parser_rejects_unrecognized_dangerous_action_types(dangerous_action):
    payload = {
        "summary": "Add greeting",
        "files": ["src/app.py"],
        "steps": ["Implement greeting"],
        "expected_behavior": "Greeting is returned",
        "acceptance_criteria": ["Tests pass"],
        "validation_commands": ["python -m pytest"],
        "potential_dangerous_actions": [dangerous_action],
        "estimated_iterations": 1,
    }

    with pytest.raises(InvalidLLMResponse):
        llm.parse_plan_response(json.dumps(payload))


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


def test_openai_compatible_client_generates_structured_plan():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        planning_context = json.loads(body["messages"][1]["content"])
        assert planning_context["task_request"] == "add greeting"
        assert planning_context["allowed_files"] == ["src/app.py"]
        assert planning_context["validation_commands"] == ["python -m pytest"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Add greeting",
                                    "files": ["src/app.py"],
                                    "steps": ["Implement greeting"],
                                    "expected_behavior": "Greeting is returned",
                                    "acceptance_criteria": ["Tests pass"],
                                    "validation_commands": ["python -m pytest"],
                                    "potential_dangerous_actions": [],
                                    "estimated_iterations": 1,
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleClient(
        base_url="https://provider.test/v1",
        model="glm-5.2",
        provider="demo",
        credential_provider=Credentials(),
        transport=httpx.MockTransport(handler),
    )

    plan = client.generate_plan(
        llm.PlanningContext(
            task_request="add greeting",
            repository_summary="branch: main",
            allowed_files=("src/app.py",),
            validation_commands=("python -m pytest",),
        )
    )

    assert plan.summary == "Add greeting"
    assert plan.files == ("src/app.py",)


def test_provider_errors_are_typed():
    transport = httpx.MockTransport(lambda request: httpx.Response(503, text="unavailable"))
    client = OpenAICompatibleClient(
        base_url="https://provider.test/v1", model="m", provider="demo",
        credential_provider=Credentials(), transport=transport,
    )
    with pytest.raises(LLMProviderError):
        client.complete(context())
