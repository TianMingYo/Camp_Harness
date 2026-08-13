import pytest

from feedbackloop.models import TaskEvent, TaskState
from feedbackloop.state import IllegalStateTransition, TaskStateMachine


def test_approved_plan_enters_running():
    machine = TaskStateMachine(TaskState.AWAITING_PLAN_APPROVAL)

    assert machine.transition(TaskEvent.PLAN_APPROVED) is TaskState.RUNNING
    assert machine.current is TaskState.RUNNING


def test_running_task_cannot_skip_to_success_without_validation():
    machine = TaskStateMachine(TaskState.RUNNING)

    assert machine.can_accept(TaskEvent.MARK_SUCCEEDED) is False
    with pytest.raises(IllegalStateTransition):
        machine.transition(TaskEvent.MARK_SUCCEEDED)


def test_objective_validation_gate_allows_success_in_two_explicit_steps():
    machine = TaskStateMachine(TaskState.RUNNING)

    assert machine.transition(TaskEvent.VALIDATION_PASSED) is TaskState.VALIDATION_PASSED
    assert machine.transition(TaskEvent.MARK_SUCCEEDED) is TaskState.SUCCEEDED


def test_terminal_success_rejects_further_events():
    machine = TaskStateMachine(TaskState.SUCCEEDED)

    assert machine.can_accept(TaskEvent.FAIL) is False
    with pytest.raises(IllegalStateTransition):
        machine.transition(TaskEvent.FAIL)


def test_unknown_event_is_rejected_without_changing_state():
    machine = TaskStateMachine(TaskState.RUNNING)

    assert machine.can_accept("not-an-event") is False
    with pytest.raises(IllegalStateTransition):
        machine.transition("not-an-event")
    assert machine.current is TaskState.RUNNING
