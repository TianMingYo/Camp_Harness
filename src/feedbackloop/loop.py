from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from feedbackloop.context import ContextBuilder, FileSummary
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import LLMClient, LLMProviderError
from feedbackloop.models import (
    Action,
    Approval,
    ApprovalDecision,
    CommandResult,
    DomainModel,
    Feedback,
    FeedbackKind,
    IterationRecord,
    Task,
    TaskEvent,
    TaskState,
    ValidationCommand,
)
from feedbackloop.policy import DecisionKind, PolicyEngine
from feedbackloop.state import TaskStateMachine
from feedbackloop.store import Store
from feedbackloop.workspace import Workspace


class LoopExecutor(Protocol):
    workspace: Workspace

    def apply(self, action: Action) -> None: ...
    def validate(self, command: ValidationCommand) -> CommandResult: ...
    def fingerprint(self) -> str: ...
    def file_summaries(self) -> list[FileSummary]: ...


class TaskResult(DomainModel):
    task_id: str
    state: TaskState
    iterations: tuple[IterationRecord, ...]
    pending_approval: Approval | None = None


class FeedbackLoop:
    def __init__(
        self,
        *,
        task_store: Store,
        llm: LLMClient,
        policy: PolicyEngine,
        executor: LoopExecutor,
        classifier: FeedbackClassifier,
        context_builder: ContextBuilder,
        max_iterations: int = 5,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        self.store = task_store
        self.llm = llm
        self.policy = policy
        self.executor = executor
        self.classifier = classifier
        self.context_builder = context_builder
        self.max_iterations = max_iterations

    def approve_plan(self, task_id: str) -> TaskState:
        task = self._task(task_id)
        machine = TaskStateMachine(task.state)
        state = machine.transition(TaskEvent.PLAN_APPROVED)
        self.store.update_task(task.model_copy(update={"state": state}))
        return state

    def run(self, task_id: str) -> TaskResult:
        task = self._task(task_id)
        if task.state is not TaskState.RUNNING:
            raise ValueError("task must have an approved plan before execution")
        plan = self.store.get_plan(task_id)
        if plan is None:
            raise ValueError("task has no approved plan")

        machine = TaskStateMachine(task.state)
        existing_iterations = self.store.list_iterations(task_id)
        previous_feedback = (
            existing_iterations[-1].feedback if existing_iterations else None
        )
        unchanged_rounds = 0
        limit = min(task.max_iterations, self.max_iterations)

        for number in range(len(existing_iterations) + 1, limit + 1):
            before = self.executor.fingerprint()
            context = self.context_builder.build(
                task,
                plan,
                self.store.list_iterations(task_id),
                self.executor.file_summaries(),
            )
            try:
                response = self.llm.complete(context)
            except LLMProviderError as error:
                feedback = Feedback(
                    kind=FeedbackKind.COMMAND_ERROR,
                    summary=str(error),
                )
                record = self._record(task_id, number, before, feedback)
                feedback = feedback.model_copy(update={"iteration_id": record.id})
                record = record.model_copy(update={"feedback": feedback})
                self._persist_iteration(record, feedback, [])
                state = machine.transition(TaskEvent.FAIL)
                self._update_state(task, state)
                return self._result(task_id, state)
            prepared_actions: list[Action] = []

            for proposed in response.actions:
                decision = self.policy.check(proposed, self.executor.workspace)
                if decision.kind is DecisionKind.DENY:
                    feedback = Feedback(
                        iteration_id=None,
                        kind=FeedbackKind.POLICY_BLOCKED,
                        summary=decision.reason,
                    )
                    record = self._record(task_id, number, before, feedback)
                    feedback = feedback.model_copy(update={"iteration_id": record.id})
                    record = record.model_copy(update={"feedback": feedback})
                    self._persist_iteration(record, feedback, [])
                    state = machine.transition(TaskEvent.FAIL)
                    self._update_state(task, state)
                    return self._result(task_id, state)

                action = proposed.model_copy(update={"iteration_id": None})
                if decision.kind is DecisionKind.REQUIRE_APPROVAL:
                    feedback = Feedback(
                        kind=FeedbackKind.POLICY_BLOCKED, summary=decision.reason
                    )
                    record = self._record(task_id, number, before, feedback)
                    action = action.model_copy(update={"iteration_id": record.id})
                    feedback = feedback.model_copy(update={"iteration_id": record.id})
                    record = record.model_copy(update={"feedback": feedback})
                    self._persist_iteration(record, feedback, [action])
                    approval = Approval(action_id=action.id, reason=decision.reason)
                    self.store.save_approval(approval)
                    state = machine.transition(TaskEvent.APPROVAL_REQUIRED)
                    self._update_state(task, state)
                    return self._result(task_id, state, approval)
                prepared_actions.append(action)

            for action in prepared_actions:
                self.executor.apply(action)

            after = self.executor.fingerprint()
            command_result = self._validate(task.validation_commands)
            feedback = self.classifier.classify(command_result, before, after)
            record = self._record(task_id, number, after, feedback)
            feedback = feedback.model_copy(update={"iteration_id": record.id})
            actions = [action.model_copy(update={"iteration_id": record.id}) for action in prepared_actions]
            record = record.model_copy(update={"feedback": feedback})
            self._persist_iteration(record, feedback, actions)

            equivalent = (
                before == after
                and previous_feedback is not None
                and previous_feedback.kind is feedback.kind
                and previous_feedback.summary == feedback.summary
            )
            unchanged_rounds = unchanged_rounds + 1 if equivalent else (1 if before == after else 0)
            previous_feedback = feedback

            if feedback.kind is FeedbackKind.PASS:
                machine.transition(TaskEvent.VALIDATION_PASSED)
                state = machine.transition(TaskEvent.MARK_SUCCEEDED)
                self._update_state(task, state)
                return self._result(task_id, state)
            if unchanged_rounds >= 2:
                state = machine.transition(TaskEvent.NO_PROGRESS)
                self._update_state(task, state)
                return self._result(task_id, state)
            if feedback.kind is FeedbackKind.TIMEOUT:
                state = machine.transition(TaskEvent.FAIL)
                self._update_state(task, state)
                return self._result(task_id, state)

        state = machine.transition(TaskEvent.MAX_ITERATIONS_REACHED)
        self._update_state(task, state)
        return self._result(task_id, state)

    def resolve_approval(
        self, approval_id: str, decision: ApprovalDecision
    ) -> TaskState:
        approval = self.store.get_approval_by_id(approval_id)
        if approval is None:
            raise KeyError(approval_id)
        action = self.store.get_action(approval.action_id)
        if action is None or action.iteration_id is None:
            raise ValueError("approval action is not attached to an iteration")
        iteration = self.store.get_iteration(action.iteration_id)
        if iteration is None:
            raise ValueError("approval iteration is missing")
        task = self._task(iteration.task_id)
        event = (
            TaskEvent.APPROVAL_GRANTED
            if decision is ApprovalDecision.ALLOWED
            else TaskEvent.APPROVAL_DENIED
        )
        state = TaskStateMachine(task.state).transition(event)
        decided = approval.model_copy(
            update={"decision": decision, "decided_at": datetime.now(UTC)}
        )
        self.store.save_approval(decided)
        if decision is ApprovalDecision.ALLOWED:
            try:
                self.executor.apply(action)
            except (OSError, RuntimeError, ValueError) as error:
                failed = TaskStateMachine(state).transition(TaskEvent.FAIL)
                self._update_state(task, failed)
                raise ValueError("approved action execution failed") from error
        self._update_state(task, state)
        return state

    def _validate(self, commands: tuple[ValidationCommand, ...]) -> CommandResult:
        if not commands:
            return CommandResult(kind="test", exit_code=0)
        result: CommandResult | None = None
        for command in commands:
            result = self.executor.validate(command)
            if result.timed_out or result.error or result.exit_code != 0:
                return result
        assert result is not None
        return result

    def _record(
        self, task_id: str, number: int, fingerprint: str, feedback: Feedback
    ) -> IterationRecord:
        return IterationRecord(
            task_id=task_id,
            number=number,
            workspace_fingerprint=fingerprint,
            result_code=feedback.exit_code,
            feedback=feedback,
            progressed=False,
            ended_at=datetime.now(UTC),
        )

    def _persist_iteration(
        self,
        record: IterationRecord,
        feedback: Feedback,
        actions: list[Action],
    ) -> None:
        self.store.save_iteration(record)
        for action in actions:
            self.store.save_action(action)
        self.store.save_feedback(feedback)

    def _task(self, task_id: str) -> Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _update_state(self, task: Task, state: TaskState) -> None:
        self.store.update_task(task.model_copy(update={"state": state}))

    def _result(
        self,
        task_id: str,
        state: TaskState,
        pending: Approval | None = None,
    ) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            state=state,
            iterations=tuple(self.store.list_iterations(task_id)),
            pending_approval=pending,
        )
