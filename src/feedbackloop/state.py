from __future__ import annotations

from feedbackloop.models import TaskEvent, TaskState


class IllegalStateTransition(ValueError):
    """Raised when an event is not legal for the current task state."""


TRANSITIONS: dict[tuple[TaskState, TaskEvent], TaskState] = {
    (TaskState.DRAFT, TaskEvent.PLAN_READY): TaskState.AWAITING_PLAN_APPROVAL,
    (TaskState.AWAITING_PLAN_APPROVAL, TaskEvent.PLAN_APPROVED): TaskState.RUNNING,
    (TaskState.RUNNING, TaskEvent.VALIDATION_PASSED): TaskState.VALIDATION_PASSED,
    (TaskState.VALIDATION_PASSED, TaskEvent.MARK_SUCCEEDED): TaskState.SUCCEEDED,
    (TaskState.RUNNING, TaskEvent.APPROVAL_REQUIRED): TaskState.AWAITING_ACTION_APPROVAL,
    (TaskState.AWAITING_ACTION_APPROVAL, TaskEvent.APPROVAL_GRANTED): TaskState.RUNNING,
    (TaskState.AWAITING_ACTION_APPROVAL, TaskEvent.APPROVAL_DENIED): TaskState.FAILED,
    (TaskState.RUNNING, TaskEvent.NO_PROGRESS): TaskState.PAUSED_NO_PROGRESS,
    (TaskState.RUNNING, TaskEvent.MAX_ITERATIONS_REACHED): TaskState.PAUSED_MAX_ITERATIONS,
    (TaskState.RUNNING, TaskEvent.FAIL): TaskState.FAILED,
    (TaskState.DRAFT, TaskEvent.CANCEL): TaskState.CANCELLED,
    (TaskState.AWAITING_PLAN_APPROVAL, TaskEvent.CANCEL): TaskState.CANCELLED,
    (TaskState.RUNNING, TaskEvent.CANCEL): TaskState.CANCELLED,
    (TaskState.AWAITING_ACTION_APPROVAL, TaskEvent.CANCEL): TaskState.CANCELLED,
}


class TaskStateMachine:
    def __init__(self, current: TaskState) -> None:
        self.current = current

    def can_accept(self, event: TaskEvent) -> bool:
        try:
            typed_event = TaskEvent(event)
        except (TypeError, ValueError):
            return False
        return (self.current, typed_event) in TRANSITIONS

    def transition(self, event: TaskEvent) -> TaskState:
        try:
            typed_event = TaskEvent(event)
            next_state = TRANSITIONS[(self.current, typed_event)]
        except (TypeError, ValueError, KeyError) as error:
            raise IllegalStateTransition(
                f"event {event!r} is illegal from state {self.current.value!r}"
            ) from error
        self.current = next_state
        return next_state
