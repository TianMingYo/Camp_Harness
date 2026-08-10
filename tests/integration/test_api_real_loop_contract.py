from collections import deque
from pathlib import Path

from fastapi.testclient import TestClient

from feedbackloop.api import create_app
from feedbackloop.context import ContextBuilder, Plan
from feedbackloop.credentials import CredentialService
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import LLMResponse, MockLLM
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import Action, ApprovalDecision, CommandResult, Task, TaskState, ValidationCommand
from feedbackloop.policy import PolicyEngine
from feedbackloop.store import Store
from feedbackloop.workspace import Workspace


class MemoryKeyring:
    def get(self, provider): return None
    def set(self, provider, key): pass
    def delete(self, provider): pass


class Executor:
    def __init__(self, root): self.workspace = Workspace(root)
    def fingerprint(self): return self.workspace.fingerprint()
    def file_summaries(self): return []
    def apply(self, action): pass
    def validate(self, command): raise AssertionError("background run is not executed in this contract test")


def test_created_plan_can_be_approved_by_real_loop(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    store = Store(tmp_path / "tasks.sqlite3")
    loop = FeedbackLoop(
        task_store=store, llm=MockLLM([]), policy=PolicyEngine(),
        executor=Executor(repo), classifier=FeedbackClassifier(),
        context_builder=ContextBuilder(),
    )
    client = TestClient(create_app(
        store=store, loop=loop, credentials=CredentialService(MemoryKeyring())
    ))
    task_id = client.post("/tasks", json={"repo_root": str(repo), "request": "feature"}).json()["id"]

    assert loop.approve_plan(task_id).value == "running"


class ResumableExecutor:
    def __init__(self, root, results):
        self.workspace = Workspace(root)
        self.results = deque(results)

    def fingerprint(self):
        return self.workspace.fingerprint()

    def file_summaries(self):
        return []

    def apply(self, action):
        if action.type.value == "delete":
            self.workspace.resolve_child(action.path_or_command).unlink()

    def validate(self, command):
        return self.results.popleft()


def test_approval_endpoint_resumes_real_loop_in_background(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "old.txt").write_text("obsolete", encoding="utf-8")
    store = Store(tmp_path / "tasks.sqlite3")
    task = Task.create(
        repo_root=str(repo),
        request="remove obsolete file",
        validation_commands=(ValidationCommand(kind="test", executable="test"),),
        state=TaskState.AWAITING_PLAN_APPROVAL,
    )
    store.create_task(task)
    store.save_plan(task.id, Plan(summary="remove obsolete file"))
    loop = FeedbackLoop(
        task_store=store,
        llm=MockLLM(
            [
                LLMResponse(actions=(Action.delete("old.txt"),)),
                LLMResponse(actions=()),
            ]
        ),
        policy=PolicyEngine(),
        executor=ResumableExecutor(
            repo, [CommandResult(kind="test", exit_code=0, stdout="passed")]
        ),
        classifier=FeedbackClassifier(),
        context_builder=ContextBuilder(),
    )
    loop.approve_plan(task.id)
    paused = loop.run(task.id)
    client = TestClient(
        create_app(
            store=store,
            loop=loop,
            credentials=CredentialService(MemoryKeyring()),
        )
    )
    status = client.get(f"/tasks/{task.id}")

    assert status.json()["approvals"] == [
        {
            "id": paused.pending_approval.id,
            "action_id": paused.pending_approval.action_id,
            "reason": "file deletion requires approval",
            "decision": "pending",
            "decided_at": None,
        }
    ]

    response = client.post(
        f"/approvals/{paused.pending_approval.id}",
        json={"decision": ApprovalDecision.ALLOWED.value},
    )

    assert response.status_code == 200
    assert store.get_task(task.id).state is TaskState.SUCCEEDED
    assert [item.number for item in store.list_iterations(task.id)] == [1, 2]
