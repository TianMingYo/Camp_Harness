from collections import deque
from pathlib import Path

from feedbackloop.context import ContextBuilder, FileSummary, Plan
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import LLMResponse, MockLLM
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import (
    Action,
    ApprovalDecision,
    ActionStatus,
    CommandResult,
    FeedbackKind,
    Task,
    TaskState,
    ValidationCommand,
)
from feedbackloop.policy import PolicyEngine
from feedbackloop.store import Store
from feedbackloop.workspace import Workspace
from tests.helpers import init_git_repo


class FakeExecutor:
    def __init__(self, root: Path, results: list[CommandResult]):
        root.mkdir(parents=True)
        init_git_repo(root)
        self.workspace = Workspace(root)
        self.results = deque(results)

    def apply(self, action: Action) -> None:
        if action.type.value == "write":
            path = self.workspace.resolve_child(action.path_or_command)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.content or "", encoding="utf-8")
        if action.type.value == "delete":
            self.workspace.resolve_child(action.path_or_command).unlink()

    def validate(self, command: ValidationCommand) -> CommandResult:
        return self.results.popleft()

    def fingerprint(self) -> str:
        return self.workspace.fingerprint()

    def file_summaries(self) -> list[FileSummary]:
        return []


def setup_loop(tmp_path: Path, responses, results):
    store = Store(tmp_path / "tasks.sqlite3")
    task = Task.create(
        repo_root=str(tmp_path / "repo"),
        request="add greeting",
        validation_commands=(ValidationCommand(kind="test", executable="pytest"),),
        state=TaskState.AWAITING_PLAN_APPROVAL,
    )
    store.create_task(task)
    store.save_plan(task.id, Plan(summary="write greeting"))
    executor = FakeExecutor(tmp_path / "repo", results)
    loop = FeedbackLoop(
        task_store=store,
        llm=MockLLM(responses),
        policy=PolicyEngine(),
        executor=executor,
        classifier=FeedbackClassifier(),
        context_builder=ContextBuilder(),
        max_iterations=5,
    )
    return task, store, loop


def test_loop_uses_failure_feedback_to_reach_pass(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [
            LLMResponse(actions=(Action.write("src/greeting.py", "return broken"),)),
            LLMResponse(actions=(Action.write("src/greeting.py", "return fixed"),)),
        ],
        [
            CommandResult(kind="test", exit_code=1, stdout="FAILED"),
            CommandResult(kind="test", exit_code=0, stdout="passed"),
        ],
    )
    assert loop.approve_plan(task.id) is TaskState.RUNNING

    result = loop.run(task.id)

    assert result.state is TaskState.SUCCEEDED
    assert [item.feedback.kind for item in result.iterations] == [
        FeedbackKind.TEST_FAILURE,
        FeedbackKind.PASS,
    ]
    assert store.get_task(task.id).state is TaskState.SUCCEEDED
    actions = [
        store.get_action(action.id)
        for record in result.iterations
        for action in store.list_actions(record.id)
    ]
    assert all(action.status is ActionStatus.COMPLETED for action in actions)


def test_two_equivalent_rounds_pause_for_no_progress(tmp_path: Path):
    task, _, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=()), LLMResponse(actions=())],
        [
            CommandResult(kind="test", exit_code=1, stdout="same failure"),
            CommandResult(kind="test", exit_code=1, stdout="same failure"),
        ],
    )
    loop.approve_plan(task.id)
    result = loop.run(task.id)
    assert result.state is TaskState.PAUSED_NO_PROGRESS
    assert len(result.iterations) == 2


def test_provider_failure_records_feedback_and_fails_task(tmp_path: Path):
    task, store, loop = setup_loop(tmp_path, [], [])
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.FAILED
    assert store.get_task(task.id).state is TaskState.FAILED
    assert len(result.iterations) == 1
    assert result.iterations[0].feedback.kind is FeedbackKind.COMMAND_ERROR


def test_loop_cannot_succeed_without_objective_validation(tmp_path: Path):
    task, store, loop = setup_loop(tmp_path, [LLMResponse(actions=())], [])
    task = task.model_copy(update={"validation_commands": ()})
    store.update_task(task)
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.FAILED
    assert result.iterations[0].feedback.kind is FeedbackKind.COMMAND_ERROR


def test_executor_exception_records_feedback_instead_of_leaving_task_running(
    tmp_path: Path,
):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=(Action.write("src/greeting.py", "value = 1\n"),))],
        [],
    )

    def fail_apply(action):
        raise OSError("disk write failed")

    loop.executor.apply = fail_apply
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.FAILED
    assert store.get_task(task.id).state is TaskState.FAILED
    assert result.iterations[0].feedback.kind is FeedbackKind.COMMAND_ERROR
    assert "disk write failed" in result.iterations[0].feedback.summary


def test_dangerous_action_pauses_for_approval(tmp_path: Path):
    task, _, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=(Action.delete("old.txt"),))],
        [],
    )
    (Path(task.repo_root) / "old.txt").write_text("obsolete", encoding="utf-8")
    loop.approve_plan(task.id)
    result = loop.run(task.id)
    assert result.state is TaskState.AWAITING_ACTION_APPROVAL
    assert result.pending_approval is not None

    assert loop.resolve_approval(result.pending_approval.id, ApprovalDecision.ALLOWED) is TaskState.RUNNING


def test_approved_action_is_applied_before_loop_resumes_at_next_iteration(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [
            LLMResponse(actions=(Action.delete("old.txt"),)),
            LLMResponse(actions=()),
        ],
        [CommandResult(kind="test", exit_code=0, stdout="passed")],
    )
    old_file = Path(task.repo_root) / "old.txt"
    old_file.write_text("obsolete", encoding="utf-8")
    loop.approve_plan(task.id)
    paused = loop.run(task.id)

    assert loop.resolve_approval(
        paused.pending_approval.id, ApprovalDecision.ALLOWED
    ) is TaskState.RUNNING
    assert not old_file.exists()
    assert store.get_action(paused.pending_approval.action_id).status is ActionStatus.COMPLETED
    assert store.list_audit_events(task.id)[-1]["kind"] == "approval_allowed"

    resumed = loop.run(task.id)

    assert resumed.state is TaskState.SUCCEEDED
    assert [item.number for item in store.list_iterations(task.id)] == [1, 2]
