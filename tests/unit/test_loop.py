from collections import deque
from pathlib import Path

import pytest

from feedbackloop.context import ContextBuilder, FileSummary, Plan
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import LLMResponse, MockLLM
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import (
    Action,
    ApprovalDecision,
    ActionStatus,
    CommandResult,
    Feedback,
    FeedbackKind,
    IterationRecord,
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
    assert all(item.progressed is True for item in result.iterations)
    actions = [
        store.get_action(action.id)
        for record in result.iterations
        for action in store.list_actions(record.id)
    ]
    assert all(action.status is ActionStatus.COMPLETED for action in actions)
    transitions = [
        event["payload"]
        for event in store.list_audit_events(task.id)
        if event["kind"] == "state_transition"
    ]
    assert transitions[-2:] == [
        {"from": "running", "to": "validation_passed"},
        {"from": "validation_passed", "to": "succeeded"},
    ]


def test_two_equivalent_rounds_pause_for_no_progress(tmp_path: Path):
    task, store, loop = setup_loop(
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
    assert result.iterations[-1].feedback.kind is FeedbackKind.NO_PROGRESS
    assert store.list_audit_events(task.id)[-1] == {
        "kind": "stop_no_progress",
        "payload": {"iterations": 2},
    }


def test_iteration_limit_pauses_with_explicit_stop_audit(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=())],
        [CommandResult(kind="test", exit_code=1, stdout="still failing")],
    )
    store.update_task(task.model_copy(update={"max_iterations": 1}))
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.PAUSED_MAX_ITERATIONS
    assert len(result.iterations) == 1
    assert store.list_audit_events(task.id)[-1] == {
        "kind": "stop_max_iterations",
        "payload": {"iterations": 1},
    }


def test_no_progress_streak_is_reconstructed_from_persisted_iterations(
    tmp_path: Path,
):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=())],
        [CommandResult(kind="test", exit_code=1, stdout="same failure")],
    )
    loop.approve_plan(task.id)
    fingerprint = loop.executor.fingerprint()
    feedback = Feedback(
        kind=FeedbackKind.TEST_FAILURE,
        exit_code=1,
        summary="same failure",
    )
    previous = IterationRecord(
        task_id=task.id,
        number=1,
        workspace_fingerprint=fingerprint,
        feedback=feedback,
        progressed=False,
    )
    feedback = feedback.model_copy(update={"iteration_id": previous.id})
    previous = previous.model_copy(update={"feedback": feedback})
    store.save_iteration(previous)
    store.save_feedback(feedback)

    result = loop.run(task.id)

    assert result.state is TaskState.PAUSED_NO_PROGRESS
    assert len(result.iterations) == 2
    assert result.iterations[-1].feedback.kind is FeedbackKind.NO_PROGRESS


def test_plan_approval_persists_timestamp_and_state_audit(tmp_path: Path):
    task, store, loop = setup_loop(tmp_path, [], [])

    assert loop.approve_plan(task.id) is TaskState.RUNNING

    assert store.get_plan(task.id).approved_at is not None
    assert store.list_audit_events(task.id)[-1]["kind"] == "state_transition"
    assert store.list_audit_events(task.id)[-1]["payload"] == {
        "from": "awaiting_plan_approval",
        "to": "running",
    }


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


def test_partial_action_failure_persists_each_action_outcome(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [
            LLMResponse(
                actions=(
                    Action.write("src/first.py", "value = 1\n"),
                    Action.write("src/second.py", "value = 2\n"),
                )
            )
        ],
        [],
    )
    apply = loop.executor.apply
    calls = 0

    def fail_second_action(action):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("second write failed")
        apply(action)

    loop.executor.apply = fail_second_action
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.FAILED
    assert (Path(task.repo_root) / "src" / "first.py").read_text(
        encoding="utf-8"
    ) == "value = 1\n"
    actions = store.list_actions(result.iterations[0].id)
    assert [action.status for action in actions] == [
        ActionStatus.COMPLETED,
        ActionStatus.FAILED,
    ]
    assert result.iterations[0].progressed is True
    assert actions[1].result_summary == "second write failed"
    assert [
        event["kind"]
        for event in store.list_audit_events(task.id)
        if event["kind"].startswith("action_")
    ] == ["action_completed", "action_failed"]


def test_validation_exception_updates_existing_iteration_and_fails_task(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=(Action.write("src/first.py", "value = 1\n"),))],
        [],
    )

    def fail_validation(command):
        raise OSError("validator crashed")

    loop.executor.validate = fail_validation
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.FAILED
    assert store.get_task(task.id).state is TaskState.FAILED
    assert len(result.iterations) == 1
    assert result.iterations[0].feedback.kind is FeedbackKind.COMMAND_ERROR
    assert result.iterations[0].progressed is True
    assert "validator crashed" in result.iterations[0].feedback.summary
    assert store.list_actions(result.iterations[0].id)[0].status is ActionStatus.COMPLETED


def test_post_action_fingerprint_failure_records_known_progress(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=(Action.write("src/first.py", "value = 1\n"),))],
        [],
    )
    fingerprint = loop.executor.fingerprint
    calls = 0

    def fail_after_action():
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("fingerprint unavailable")
        return fingerprint()

    loop.executor.fingerprint = fail_after_action
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.FAILED
    assert len(result.iterations) == 1
    assert result.iterations[0].progressed is True
    assert result.iterations[0].workspace_fingerprint == "unavailable"
    assert store.list_actions(result.iterations[0].id)[0].status is (
        ActionStatus.COMPLETED
    )


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


def test_mixed_safe_and_dangerous_batch_persists_every_proposed_action(
    tmp_path: Path,
):
    task, store, loop = setup_loop(
        tmp_path,
        [
            LLMResponse(
                actions=(
                    Action.write("src/new.py", "value = 1\n"),
                    Action.delete("old.txt"),
                )
            )
        ],
        [],
    )
    (Path(task.repo_root) / "old.txt").write_text("obsolete", encoding="utf-8")
    loop.approve_plan(task.id)

    result = loop.run(task.id)

    assert result.state is TaskState.AWAITING_ACTION_APPROVAL
    new_file = Path(task.repo_root) / "src" / "new.py"
    assert not new_file.exists()
    actions = store.list_actions(result.iterations[0].id)
    assert [action.path_or_command for action in actions] == [
        "src/new.py",
        "old.txt",
    ]
    assert [action.status for action in actions] == [
        ActionStatus.PROPOSED,
        ActionStatus.PROPOSED,
    ]
    assert result.pending_approval.action_id == actions[1].id

    loop.resolve_approval(result.pending_approval.id, ApprovalDecision.ALLOWED)

    assert new_file.read_text(encoding="utf-8") == "value = 1\n"
    assert [
        action.status for action in store.list_actions(result.iterations[0].id)
    ] == [ActionStatus.COMPLETED, ActionStatus.COMPLETED]


def test_approval_batch_preserves_model_action_order(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [
            LLMResponse(
                actions=(
                    Action.delete("same.txt"),
                    Action.write("same.txt", "replacement"),
                )
            )
        ],
        [],
    )
    target = Path(task.repo_root) / "same.txt"
    target.write_text("original", encoding="utf-8")
    loop.approve_plan(task.id)

    paused = loop.run(task.id)

    assert paused.state is TaskState.AWAITING_ACTION_APPROVAL
    assert target.read_text(encoding="utf-8") == "original"
    assert [
        action.status for action in store.list_actions(paused.iterations[0].id)
    ] == [ActionStatus.PROPOSED, ActionStatus.PROPOSED]

    assert loop.resolve_approval(
        paused.pending_approval.id, ApprovalDecision.ALLOWED
    ) is TaskState.RUNNING
    assert target.read_text(encoding="utf-8") == "replacement"
    assert [
        action.status for action in store.list_actions(paused.iterations[0].id)
    ] == [ActionStatus.COMPLETED, ActionStatus.COMPLETED]


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


def test_approved_action_failure_marks_action_and_audits_real_transitions(
    tmp_path: Path,
):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=(Action.delete("old.txt"),))],
        [],
    )
    old_file = Path(task.repo_root) / "old.txt"
    old_file.write_text("obsolete", encoding="utf-8")
    loop.approve_plan(task.id)
    paused = loop.run(task.id)
    old_file.unlink()

    with pytest.raises(ValueError, match="execution failed"):
        loop.resolve_approval(paused.pending_approval.id, ApprovalDecision.ALLOWED)

    action = store.get_action(paused.pending_approval.action_id)
    assert action.status is ActionStatus.FAILED
    assert action.result_summary
    assert store.get_approval_by_id(paused.pending_approval.id).decision is (
        ApprovalDecision.ALLOWED
    )
    assert store.get_task(task.id).state is TaskState.FAILED
    transitions = [
        event["payload"]
        for event in store.list_audit_events(task.id)
        if event["kind"] == "state_transition"
    ]
    assert transitions[-2:] == [
        {"from": "awaiting_action_approval", "to": "running"},
        {"from": "running", "to": "failed"},
    ]
    assert store.list_audit_events(task.id)[-1]["kind"] == (
        "approval_execution_failed"
    )


def test_unexpected_approved_action_exception_is_controlled(tmp_path: Path):
    task, store, loop = setup_loop(
        tmp_path,
        [LLMResponse(actions=(Action.delete("old.txt"),))],
        [],
    )
    old_file = Path(task.repo_root) / "old.txt"
    old_file.write_text("obsolete", encoding="utf-8")
    loop.approve_plan(task.id)
    paused = loop.run(task.id)

    def fail_apply(action):
        raise AssertionError("unexpected executor failure")

    loop.executor.apply = fail_apply

    with pytest.raises(ValueError, match="execution failed"):
        loop.resolve_approval(paused.pending_approval.id, ApprovalDecision.ALLOWED)

    action = store.get_action(paused.pending_approval.action_id)
    assert action.status is ActionStatus.FAILED
    assert "unexpected executor failure" in action.result_summary
    assert store.get_task(task.id).state is TaskState.FAILED
