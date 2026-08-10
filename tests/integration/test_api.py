from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from feedbackloop.api import create_app
from feedbackloop.credentials import CredentialService
from feedbackloop.llm import LLMResponse, OpenAICompatibleClient
from feedbackloop.store import Store
from feedbackloop.models import ApprovalDecision, TaskState


class MemoryKeyring:
    def __init__(self):
        self.values = {}

    def get(self, provider):
        return self.values.get(provider)

    def set(self, provider, key):
        self.values[provider] = key

    def delete(self, provider):
        self.values.pop(provider, None)


class StubLoop:
    def __init__(self):
        self.approvals = []

    def approve_plan(self, task_id):
        return TaskState.RUNNING

    def run(self, task_id):
        return None

    def resolve_approval(self, approval_id, decision):
        self.approvals.append((approval_id, decision))
        return TaskState.RUNNING


def client(tmp_path: Path, *, public_demo: bool = False):
    store = Store(tmp_path / "tasks.sqlite3")
    loop = StubLoop()
    app = create_app(
        store=store,
        loop=loop,
        credentials=CredentialService(MemoryKeyring()),
        demo=True,
        public_demo=public_demo,
    )
    return TestClient(app), loop


def test_task_create_approve_and_get_status(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    created = test_client.post("/tasks", json={"repo_root": str(repo), "request": "add greeting"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["state"] == "awaiting_plan_approval"

    approved = test_client.post(f"/tasks/{task_id}/plan/approve")
    assert approved.status_code == 202
    assert approved.json()["state"] == "running"
    status = test_client.get(f"/tasks/{task_id}")
    assert status.status_code == 200
    assert status.json()["task"]["id"] == task_id
    assert status.json()["plan"]["summary"] == "add greeting"
    assert status.json()["task"]["validation_commands"][0]["kind"] == "test"


def test_credentials_never_echo_key_and_demo_is_available(tmp_path: Path):
    test_client, _ = client(tmp_path)
    response = test_client.post("/providers/demo/credentials", json={"key": "secret-value"})
    assert response.status_code == 200
    assert "secret-value" not in response.text
    assert response.json()["configured"] is True

    demo = test_client.get("/demo/scenario")
    assert demo.status_code == 200
    assert demo.json()["mode"] == "mock"

    cleared = test_client.delete("/providers/demo/credentials")
    assert cleared.status_code == 200
    assert cleared.json()["configured"] is False


def test_approval_endpoint_delegates_decision(tmp_path: Path):
    test_client, loop = client(tmp_path)
    response = test_client.post("/approvals/approval-1", json={"decision": "allowed"})
    assert response.status_code == 200
    assert loop.approvals == [("approval-1", ApprovalDecision.ALLOWED)]


def test_public_demo_rejects_local_repo_path(tmp_path: Path):
    test_client, _ = client(tmp_path, public_demo=True)
    response = test_client.post(
        "/tasks", json={"repo_root": str(tmp_path), "request": "read local"}
    )
    assert response.status_code == 400


def test_public_demo_rejects_credentials(tmp_path: Path):
    test_client, _ = client(tmp_path, public_demo=True)
    response = test_client.post(
        "/providers/demo/credentials", json={"key": "must-not-be-stored"}
    )
    assert response.status_code == 403
    assert "must-not-be-stored" not in response.text


def test_webui_root_is_accessible(tmp_path: Path):
    test_client, _ = client(tmp_path)
    response = test_client.get("/")
    assert response.status_code == 200
    assert "Feedback Loop" in response.text


def test_webui_exposes_local_provider_and_validation_configuration(tmp_path: Path):
    class InputCollector(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if attributes.get("id"):
                self.ids.add(attributes["id"])

    test_client, _ = client(tmp_path)
    response = test_client.get("/")
    parser = InputCollector()
    parser.feed(response.text)

    assert {
        "provider",
        "base-url",
        "model",
        "validation-executable",
        "validation-args",
        "pending-approvals",
    } <= parser.ids


def test_task_creation_uses_structured_validation_overrides(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "lint the project",
            "validation_commands": [
                {
                    "kind": "lint",
                    "executable": "python",
                    "args": ["-m", "ruff", "check", "."],
                }
            ],
        },
    )

    assert created.status_code == 201
    assert created.json()["validation_commands"] == [
        {
            "kind": "lint",
            "executable": "python",
            "args": ["-m", "ruff", "check", "."],
            "timeout_seconds": 120.0,
            "auto_execute": True,
        }
    ]


def test_default_local_app_builds_real_loop_from_task_provider_config(
    tmp_path: Path, monkeypatch
):
    captured = {}

    def complete(client, context):
        captured.update(
            provider=client.provider,
            base_url=client.base_url,
            model=client.model,
            request=context.task_request,
        )
        return LLMResponse(actions=())

    monkeypatch.setattr(OpenAICompatibleClient, "complete", complete)
    store = Store(tmp_path / "local.sqlite3")
    test_client = TestClient(
        create_app(store=store, credentials=CredentialService(MemoryKeyring()))
    )
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "provider": "glm",
            "base_url": "https://gateway.example/v1",
            "model": "glm-5.2",
        },
    )
    approved = test_client.post(f"/tasks/{created.json()['id']}/plan/approve")

    assert approved.status_code == 202
    assert captured == {
        "provider": "glm",
        "base_url": "https://gateway.example/v1",
        "model": "glm-5.2",
        "request": "add greeting",
    }
    assert test_client.get(f"/tasks/{created.json()['id']}").json()["task"]["state"] == (
        "succeeded"
    )
