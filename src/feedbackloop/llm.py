from __future__ import annotations

import json
from collections import deque
from typing import Protocol

import httpx
from pydantic import ValidationError

from feedbackloop.context import AgentContext
from feedbackloop.models import Action, DomainModel


class LLMProviderError(RuntimeError):
    pass


class InvalidLLMResponse(LLMProviderError):
    pass


class LLMResponse(DomainModel):
    actions: tuple[Action, ...]
    raw_content: str | None = None


class LLMClient(Protocol):
    def complete(self, context: AgentContext) -> LLMResponse: ...


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
        key = self.credential_provider.get(self.provider)
        if not key:
            raise LLMProviderError(f"credential is not configured for {self.provider}")
        request = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return one JSON object with an actions array and no prose.",
                },
                {"role": "user", "content": context.model_dump_json()},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout_seconds) as client:
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
            raise InvalidLLMResponse("provider response is missing message content") from error
        return LLMResponse(actions=parse_action_response(content), raw_content=content)
