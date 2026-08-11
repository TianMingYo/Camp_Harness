from __future__ import annotations

import json
from collections import deque
from typing import Literal, Protocol

import httpx
from pydantic import Field, ValidationError

from feedbackloop.context import AgentContext, Plan
from feedbackloop.models import Action, DomainModel


class LLMProviderError(RuntimeError):
    pass


class InvalidLLMResponse(LLMProviderError):
    def __init__(self, message: str, *, raw_content: str | None = None) -> None:
        super().__init__(message)
        self.raw_content = raw_content


class LLMResponse(DomainModel):
    actions: tuple[Action, ...]
    raw_content: str | None = None


class PlanningContext(DomainModel):
    task_request: str = Field(min_length=1)
    repository_summary: str
    allowed_files: tuple[str, ...] = Field(min_length=1)
    validation_commands: tuple[str, ...] = Field(min_length=1)


class _StructuredPlan(DomainModel):
    summary: str = Field(min_length=1)
    files: tuple[str, ...] = Field(min_length=1)
    steps: tuple[str, ...] = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    acceptance_criteria: tuple[str, ...] = Field(min_length=1)
    validation_commands: tuple[str, ...] = Field(min_length=1)
    potential_dangerous_actions: tuple[
        Literal["command", "delete", "network", "git_push"], ...
    ]
    estimated_iterations: int = Field(ge=1, le=5)


class LLMClient(Protocol):
    def complete(self, context: AgentContext) -> LLMResponse: ...


class PlanGenerator(Protocol):
    def generate_plan(self, context: PlanningContext) -> Plan: ...


class CredentialProvider(Protocol):
    def get(self, provider: str) -> str | None: ...


def parse_action_response(payload: str) -> tuple[Action, ...]:
    try:
        parsed = json.loads(payload)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("actions"), list):
            raise TypeError("response must contain an actions list")
        return tuple(Action.model_validate(item) for item in parsed["actions"])
    except (json.JSONDecodeError, TypeError, ValidationError) as error:
        raise InvalidLLMResponse("invalid structured action response") from error


def parse_plan_response(payload: str) -> Plan:
    try:
        parsed = json.loads(payload)
        structured = _StructuredPlan.model_validate(parsed)
        return Plan.model_validate(structured.model_dump())
    except (json.JSONDecodeError, TypeError, ValidationError) as error:
        raise InvalidLLMResponse(
            "invalid structured plan response", raw_content=payload
        ) from error


class MockLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = deque(responses)

    def complete(self, context: AgentContext) -> LLMResponse:
        del context
        if not self._responses:
            raise LLMProviderError("mock response sequence is exhausted")
        return self._responses.popleft()


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        credential_provider: CredentialProvider,
        provider: str = "default",
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider
        self.credential_provider = credential_provider
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def complete(self, context: AgentContext) -> LLMResponse:
        content = self._chat_json(
            "Return one JSON object with an actions array and no prose.",
            context.model_dump_json(),
        )
        return LLMResponse(actions=parse_action_response(content), raw_content=content)

    def generate_plan(self, context: PlanningContext) -> Plan:
        content = self._chat_json(
            (
                "Return one JSON plan object with summary, files, steps, "
                "expected_behavior, acceptance_criteria, validation_commands, "
                "potential_dangerous_actions, and estimated_iterations. No prose."
            ),
            context.model_dump_json(),
        )
        return parse_plan_response(content)

    def _chat_json(self, system_message: str, user_message: str) -> str:
        key = self.credential_provider.get(self.provider)
        if not key:
            raise LLMProviderError(f"credential is not configured for {self.provider}")
        request = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_message,
                },
                {"role": "user", "content": user_message},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(
                transport=self.transport, timeout=self.timeout_seconds
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=request,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise LLMProviderError("provider request failed") from error

        try:
            message = body["choices"][0]["message"]
            if message.get("refusal"):
                raise InvalidLLMResponse("provider refused the request")
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError("message content must be text")
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise InvalidLLMResponse(
                "provider response is missing message content"
            ) from error
        return content
