from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from feedbackloop.api import create_app
from feedbackloop.context import Plan
from feedbackloop.credentials import CredentialService
from feedbackloop.llm import LLMResponse, OpenAICompatibleClient, parse_plan_response
from feedbackloop.store import Store
from feedbackloop.models import ApprovalDecision, TaskState
from feedbackloop.models import Task
from tests.helpers import init_git_repo


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


class StubPlanner:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.contexts = []

    def generate_plan(self, context):
        self.contexts.append(context)
        if self.error:
            raise self.error
        return Plan(
            summary=context.task_request,
            files=context.allowed_files,
            steps=(context.task_request,),
            expected_behavior=context.task_request,
            acceptance_criteria=("configured validation passes",),
            validation_commands=context.validation_commands,
            potential_dangerous_actions=(),
            estimated_iterations=1,
        )

def client(tmp_path: Path, *, public_demo: bool = False):
    store = Store(tmp_path / "tasks.sqlite3")
    loop = StubLoop()
    app = create_app(
        store=store,
        loop=loop,
        planner=StubPlanner(),
        credentials=CredentialService(MemoryKeyring()),
        demo=True,
        public_demo=public_demo,
    )
    return TestClient(app), loop


def test_task_create_approve_and_get_status(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "plan_files": ["src/greeting.py"],
        },
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert created.json()["state"] == "draft"

    planned = test_client.get(f"/tasks/{task_id}")
    assert planned.json()["task"]["state"] == "awaiting_plan_approval"

    approved = test_client.post(f"/tasks/{task_id}/plan/approve")
    assert approved.status_code == 202
    assert approved.json()["state"] == "running"
    status = test_client.get(f"/tasks/{task_id}")
    assert status.status_code == 200
    assert status.json()["task"]["id"] == task_id
    assert status.json()["plan"]["summary"] == "add greeting"
    assert status.json()["plan"]["files"] == ["src/greeting.py"]
    assert status.json()["plan"]["steps"] == ["add greeting"]
    assert status.json()["task"]["validation_commands"][0]["kind"] == "test"
    assert status.json()["audit_events"][0]["kind"] == "plan_ready"
    assert status.json()["audit_events"][1] == {
        "kind": "state_transition",
        "payload": {"from": "draft", "to": "awaiting_plan_approval"},
    }


def test_plan_generation_failure_is_persisted_without_a_plan(tmp_path: Path):
    from feedbackloop.llm import LLMProviderError

    store = Store(tmp_path / "tasks.sqlite3")
    app = create_app(
        store=store,
        loop=StubLoop(),
        planner=StubPlanner(LLMProviderError("provider request failed")),
        credentials=CredentialService(MemoryKeyring()),
        demo=True,
    )
    test_client = TestClient(app)
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "plan_files": ["src/greeting.py"],
        },
    )

    assert created.status_code == 201
    status = test_client.get(f"/tasks/{created.json()['id']}").json()
    assert status["task"]["state"] == "failed"
    assert status["plan"] is None
    assert status["audit_events"][-2] == {
        "kind": "state_transition",
        "payload": {"from": "draft", "to": "failed"},
    }
    assert status["audit_events"][-1] == {
        "kind": "plan_generation_failed",
        "payload": {"summary": "provider request failed"},
    }


def test_unexpected_planner_exception_cannot_leave_task_in_draft(tmp_path: Path):
    store = Store(tmp_path / "tasks.sqlite3")
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            planner=StubPlanner(RuntimeError("planner crashed")),
            credentials=CredentialService(MemoryKeyring()),
            demo=True,
        )
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "plan_files": ["src/greeting.py"],
        },
    )

    status = test_client.get(f"/tasks/{created.json()['id']}").json()
    assert status["task"]["state"] == "failed"
    assert status["audit_events"][-1]["payload"]["summary"] == "planner crashed"


def test_invalid_plan_audit_keeps_only_redacted_raw_summary(tmp_path: Path):
    class InvalidPlanner:
        def generate_plan(self, context):
            del context
            return parse_plan_response(
                '{"api_key":"sk-private-value","unexpected":true}'
            )

    store = Store(tmp_path / "tasks.sqlite3")
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            planner=InvalidPlanner(),
            credentials=CredentialService(MemoryKeyring()),
            demo=True,
        )
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "plan_files": ["src/greeting.py"],
        },
    )
    response = test_client.get(f"/tasks/{created.json()['id']}")

    summary = response.json()["audit_events"][-1]["payload"]["summary"]
    assert "unexpected" in summary
    assert "sk-private-value" not in response.text
    assert "[REDACTED]" in summary


def test_planner_receives_bounded_repository_summary(tmp_path: Path):
    store = Store(tmp_path / "tasks.sqlite3")
    planner = StubPlanner()
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            planner=planner,
            credentials=CredentialService(MemoryKeyring()),
            demo=True,
        )
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )

    test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "plan_files": ["src/greeting.py"],
        },
    )

    summary = planner.contexts[0].repository_summary
    assert "branch:" in summary
    assert "pyproject.toml" in summary
    assert "status:" in summary


def test_generated_plan_cannot_expand_authorized_file_scope(tmp_path: Path):
    class ExpandingPlanner(StubPlanner):
        def generate_plan(self, context):
            return super().generate_plan(context).model_copy(
                update={"files": ("src/unapproved.py",)}
            )

    store = Store(tmp_path / "tasks.sqlite3")
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            planner=ExpandingPlanner(),
            credentials=CredentialService(MemoryKeyring()),
            demo=True,
        )
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "plan_files": ["src/greeting.py"],
        },
    )

    status = test_client.get(f"/tasks/{created.json()['id']}").json()
    assert status["task"]["state"] == "failed"
    assert status["plan"] is None
    assert "authorized file scope" in status["audit_events"][-1]["payload"]["summary"]


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"validation_commands": ("unapproved command",)}, "validation commands"),
        ({"estimated_iterations": 2}, "iteration limit"),
    ],
)
def test_generated_plan_cannot_change_harness_limits(
    tmp_path: Path, updates: dict, expected: str
):
    class LimitChangingPlanner(StubPlanner):
        def generate_plan(self, context):
            return super().generate_plan(context).model_copy(update=updates)

    store = Store(tmp_path / "tasks.sqlite3")
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            planner=LimitChangingPlanner(),
            credentials=CredentialService(MemoryKeyring()),
            demo=True,
        )
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "max_iterations": 1,
            "plan_files": ["src/greeting.py"],
            "validation_commands": [
                {"kind": "test", "executable": "python", "args": ["-c", "pass"]}
            ],
        },
    )

    status = test_client.get(f"/tasks/{created.json()['id']}").json()
    assert status["task"]["state"] == "failed"
    assert expected in status["audit_events"][-1]["payload"]["summary"]


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


def test_credential_status_is_readable_without_exposing_key(tmp_path: Path):
    test_client, _ = client(tmp_path)
    response = test_client.get("/providers/demo/credentials")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "key" not in response.text.lower()


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


def test_public_demo_cannot_read_or_execute_seeded_local_tasks(tmp_path: Path):
    store = Store(tmp_path / "shared.sqlite3")
    repo = tmp_path / "repo"
    init_git_repo(repo)
    task = Task.create(repo_root=str(repo), request="private task")
    store.create_task(task)
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            planner=StubPlanner(),
            credentials=CredentialService(MemoryKeyring()),
            demo=True,
            public_demo=True,
        )
    )

    assert test_client.get(f"/tasks/{task.id}").status_code == 404
    assert test_client.post(f"/tasks/{task.id}/plan/approve").status_code == 404
    assert test_client.post(
        "/approvals/private", json={"decision": "allowed"}
    ).status_code == 404


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
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "lint the project",
            "plan_files": ["src/module.py"],
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
            "kind": "test",
            "executable": "python",
            "args": ["-m", "pytest", "-q"],
            "timeout_seconds": 120.0,
            "auto_execute": True,
        },
        {
            "kind": "lint",
            "executable": "python",
            "args": ["-m", "ruff", "check", "."],
            "timeout_seconds": 120.0,
            "auto_execute": True,
        }
    ]


def test_task_creation_rejects_empty_validation_set(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    init_git_repo(repo)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "change code",
            "plan_files": ["src/module.py"],
        },
    )

    assert created.status_code == 400
    assert "validation" in created.text.lower()


def test_task_creation_rejects_wildcard_or_empty_plan_scope(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    for plan_files in ([], ["**"]):
        created = test_client.post(
            "/tasks",
            json={
                "repo_root": str(repo),
                "request": "change code",
                "plan_files": plan_files,
            },
        )
        assert created.status_code == 400
        assert "plan" in created.text.lower()


def test_task_creation_normalizes_plan_paths_and_rejects_unsafe_scope(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    init_git_repo(repo)
    (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    normalized = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "change readme",
            "plan_files": ["src/../README.md"],
        },
    )
    assert normalized.status_code == 201
    task_id = normalized.json()["id"]
    assert test_client.get(f"/tasks/{task_id}").json()["plan"]["files"] == ["README.md"]

    for plan_files in (
        ["../outside.py"],
        [".env"],
        [".npmrc"],
        ["secrets.json"],
        ["private.pem"],
        [""],
    ):
        rejected = test_client.post(
            "/tasks",
            json={
                "repo_root": str(repo),
                "request": "unsafe",
                "plan_files": plan_files,
            },
        )
        assert rejected.status_code == 400


def test_task_creation_preflights_validation_executable(tmp_path: Path):
    test_client, _ = client(tmp_path)
    repo = tmp_path / "repo"
    init_git_repo(repo)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "change code",
            "plan_files": ["src/module.py"],
            "validation_commands": [
                {"kind": "test", "executable": "definitely-missing-command"}
            ],
        },
    )

    assert created.status_code == 400
    assert "executable" in created.text.lower()


def test_default_local_app_requires_complete_provider_configuration(tmp_path: Path):
    store = Store(tmp_path / "local.sqlite3")
    test_client = TestClient(
        create_app(store=store, credentials=CredentialService(MemoryKeyring()))
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "change code",
            "plan_files": ["src/module.py"],
            "validation_commands": [
                {"kind": "test", "executable": "python", "args": ["-c", "pass"]}
            ],
        },
    )

    assert created.status_code == 400
    assert "provider" in created.text.lower()


def test_injected_loop_requires_explicit_planner_or_provider(tmp_path: Path):
    store = Store(tmp_path / "local.sqlite3")
    test_client = TestClient(
        create_app(
            store=store,
            loop=StubLoop(),
            credentials=CredentialService(MemoryKeyring()),
        )
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "change code",
            "plan_files": ["src/module.py"],
            "validation_commands": [
                {"kind": "test", "executable": "python", "args": ["-c", "pass"]}
            ],
        },
    )

    assert created.status_code == 400
    assert "planner" in created.text.lower()


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
    monkeypatch.setattr(
        OpenAICompatibleClient,
        "generate_plan",
        lambda client, context: StubPlanner().generate_plan(context),
    )
    store = Store(tmp_path / "local.sqlite3")
    test_client = TestClient(
        create_app(store=store, credentials=CredentialService(MemoryKeyring()))
    )
    repo = tmp_path / "repo"
    init_git_repo(repo)

    created = test_client.post(
        "/tasks",
        json={
            "repo_root": str(repo),
            "request": "add greeting",
            "provider": "glm",
            "base_url": "https://gateway.example/v1",
            "model": "glm-5.2",
            "plan_files": ["src/greeting.py"],
            "validation_commands": [
                {"kind": "test", "executable": "python", "args": ["-c", "pass"]}
            ],
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
