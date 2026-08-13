from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from feedbackloop.models import (
    Action,
    ActionStatus,
    ActionType,
    Approval,
    ApprovalDecision,
    Feedback,
    FeedbackKind,
    IterationRecord,
    Task,
    TaskState,
    ValidationCommand,
)


def test_new_task_starts_in_draft():
    task = Task.create(repo_root="/repo", request="add a greeting command")

    assert task.state is TaskState.DRAFT
    assert task.max_iterations == 5
    assert task.validation_commands == ()


def test_validation_command_rejects_unsupported_manual_execution_flag():
    with pytest.raises(ValueError, match="auto_execute"):
        ValidationCommand(
            kind="test", executable="pytest", auto_execute=False
        )


def test_task_rejects_blank_request():
    with pytest.raises(ValidationError):
        Task.create(repo_root="/repo", request="   ")


@pytest.mark.parametrize(
    ("action", "expected_type", "expected_target", "expected_content"),
    [
        (Action.read("README.md"), ActionType.READ, "README.md", None),
        (Action.write("src/app.py", "print('ok')\n"), ActionType.WRITE, "src/app.py", "print('ok')\n"),
        (Action.delete("old.txt"), ActionType.DELETE, "old.txt", None),
        (Action.command("pytest -q"), ActionType.COMMAND, "pytest -q", None),
        (Action.network("https://example.test"), ActionType.NETWORK, "https://example.test", None),
        (Action.git_push("origin/main"), ActionType.GIT_PUSH, "origin/main", None),
    ],
)
def test_action_factories_preserve_typed_proposals(
    action, expected_type, expected_target, expected_content
):
    assert action.type is expected_type
    assert action.path_or_command == expected_target
    assert action.content == expected_content
    assert action.status is ActionStatus.PROPOSED


def test_action_rejects_write_without_content():
    with pytest.raises(ValidationError):
        Action(type=ActionType.WRITE, path_or_command="src/app.py")


def test_validation_command_is_immutable_and_serializes_args_as_json_array():
    command = ValidationCommand(
        kind="test",
        executable="python",
        args=("-m", "pytest", "-q"),
        timeout_seconds=30,
    )

    assert command.model_dump(mode="json")["args"] == ["-m", "pytest", "-q"]
    with pytest.raises(ValidationError):
        command.timeout_seconds = 10


def test_iteration_record_nests_feedback_for_auditable_serialization():
    now = datetime.now(UTC)
    feedback = Feedback(
        iteration_id="iteration-1",
        kind=FeedbackKind.TEST_FAILURE,
        exit_code=1,
        summary="one test failed",
    )
    record = IterationRecord(
        id="iteration-1",
        task_id="task-1",
        number=1,
        workspace_fingerprint="abc123",
        feedback=feedback,
        progressed=True,
        started_at=now,
        ended_at=now,
    )

    payload = record.model_dump(mode="json")
    assert payload["feedback"]["kind"] == "test_failure"
    assert payload["number"] == 1


def test_approval_defaults_to_pending_without_a_decision_time():
    approval = Approval(action_id="action-1", reason="network access")

    assert approval.decision is ApprovalDecision.PENDING
    assert approval.decided_at is None
