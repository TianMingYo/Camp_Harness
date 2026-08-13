from __future__ import annotations

import json
import tempfile
import subprocess
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from feedbackloop.context import ContextBuilder, FileSummary, Plan
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import LLMResponse, MockLLM
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import Action, CommandResult, Task, TaskState, ValidationCommand
from feedbackloop.policy import DecisionKind, PolicyEngine
from feedbackloop.store import Store
from feedbackloop.workspace import Workspace


@dataclass(frozen=True)
class DemoResult:
    corrected_after_feedback: bool
    policy_blocked: bool
    used_network: bool
    final_state: str


class _DemoExecutor:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--quiet", str(root)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.workspace = Workspace(root)
        self._results = deque(
            [
                CommandResult(kind="test", exit_code=1, stdout="FAILED greeting"),
                CommandResult(kind="test", exit_code=0, stdout="1 passed"),
            ]
        )

    def apply(self, action: Action) -> None:
        if action.type.value == "write":
            path = self.workspace.resolve_child(action.path_or_command)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.content or "", encoding="utf-8")

    def validate(self, command: ValidationCommand) -> CommandResult:
        return self._results.popleft()

    def fingerprint(self) -> str:
        return self.workspace.fingerprint()

    def file_summaries(self) -> list[FileSummary]:
        return []


def run_demo() -> DemoResult:
    with tempfile.TemporaryDirectory(prefix="feedbackloop-demo-") as temporary:
        root = Path(temporary) / "sample-repo"
        executor = _DemoExecutor(root)
        store = Store(Path(temporary) / "demo.sqlite3")
        task = Task.create(
            repo_root=str(root),
            request="add greeting",
            validation_commands=(ValidationCommand(kind="test", executable="demo-test"),),
            state=TaskState.AWAITING_PLAN_APPROVAL,
        )
        store.create_task(task)
        store.save_plan(task.id, Plan(summary="write greeting"))
        loop = FeedbackLoop(
            task_store=store,
            llm=MockLLM(
                [
                    LLMResponse(actions=(Action.write("src/greeting.py", "return broken"),)),
                    LLMResponse(actions=(Action.write("src/greeting.py", "return fixed"),)),
                ]
            ),
            policy=PolicyEngine(),
            executor=executor,
            classifier=FeedbackClassifier(),
            context_builder=ContextBuilder(),
        )
        loop.approve_plan(task.id)
        result = loop.run(task.id)
        policy_decision = PolicyEngine().check(Action.delete("old.txt"), executor.workspace)
        demo_result = DemoResult(
            corrected_after_feedback=(
                result.state is TaskState.SUCCEEDED and len(result.iterations) == 2
            ),
            policy_blocked=policy_decision.kind is DecisionKind.REQUIRE_APPROVAL,
            used_network=False,
            final_state=result.state.value,
        )
        store.close()
        return demo_result


def main() -> None:
    print(json.dumps(asdict(run_demo()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
