from pathlib import Path

from fastapi.testclient import TestClient

from feedbackloop.api import create_app
from feedbackloop.context import ContextBuilder
from feedbackloop.credentials import CredentialService
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import MockLLM
from feedbackloop.loop import FeedbackLoop
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
