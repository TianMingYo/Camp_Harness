from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _new_id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class StringEnum(str, Enum):
    pass


class TaskState(StringEnum):
    DRAFT = "draft"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    RUNNING = "running"
    VALIDATION_PASSED = "validation_passed"
    AWAITING_ACTION_APPROVAL = "awaiting_action_approval"
    PAUSED_NO_PROGRESS = "paused_no_progress"
    PAUSED_MAX_ITERATIONS = "paused_max_iterations"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskEvent(StringEnum):
    PLAN_READY = "plan_ready"
    PLAN_APPROVED = "plan_approved"
    VALIDATION_PASSED = "validation_passed"
    MARK_SUCCEEDED = "mark_succeeded"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    NO_PROGRESS = "no_progress"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    FAIL = "fail"
    CANCEL = "cancel"


class ActionType(StringEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    COMMAND = "command"
    NETWORK = "network"
    GIT_PUSH = "git_push"


class ActionRisk(StringEnum):
    NORMAL = "normal"
    DANGEROUS = "dangerous"


class ActionStatus(StringEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    COMPLETED = "completed"
    FAILED = "failed"


class FeedbackKind(StringEnum):
    PASS = "pass"
    TEST_FAILURE = "test_failure"
    BUILD_FAILURE = "build_failure"
    LINT_FAILURE = "lint_failure"
    TYPE_FAILURE = "type_failure"
    TIMEOUT = "timeout"
    POLICY_BLOCKED = "policy_blocked"
    COMMAND_ERROR = "command_error"
    NO_PROGRESS = "no_progress"


class ApprovalDecision(StringEnum):
    PENDING = "pending"
    ALLOWED = "allowed"
    DENIED = "denied"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ValidationCommand(DomainModel):
    kind: str = Field(min_length=1)
    executable: str = Field(min_length=1)
    args: tuple[str, ...] = ()
    timeout_seconds: float = Field(default=120, gt=0)
    auto_execute: bool = True


class CommandResult(DomainModel):
    kind: str = Field(min_length=1)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_seconds: float = Field(default=0, ge=0)
    error: str | None = None


class Task(DomainModel):
    id: str = Field(default_factory=_new_id)
    repo_root: str = Field(min_length=1)
    request: str = Field(min_length=1)
    branch: str | None = None
    validation_commands: tuple[ValidationCommand, ...] = ()
    max_iterations: int = Field(default=5, ge=1, le=100)
    state: TaskState = TaskState.DRAFT
    created_at: datetime = Field(default_factory=_now)

    @field_validator("repo_root", "request")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @classmethod
    def create(cls, repo_root: str, request: str, **values: object) -> Self:
        return cls(repo_root=repo_root, request=request, **values)


class Action(DomainModel):
    id: str = Field(default_factory=_new_id)
    iteration_id: str | None = None
    type: ActionType
    path_or_command: str = Field(min_length=1)
    content: str | None = None
    risk: ActionRisk = ActionRisk.NORMAL
    status: ActionStatus = ActionStatus.PROPOSED
    result_summary: str | None = None

    @field_validator("path_or_command")
    @classmethod
    def reject_blank_target(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action target must not be blank")
        return value

    @model_validator(mode="after")
    def validate_content(self) -> Self:
        if self.type is ActionType.WRITE and self.content is None:
            raise ValueError("write actions require content")
        if self.type is not ActionType.WRITE and self.content is not None:
            raise ValueError("only write actions may include content")
        return self

    @classmethod
    def read(cls, path: str) -> Self:
        return cls(type=ActionType.READ, path_or_command=path)

    @classmethod
    def write(cls, path: str, content: str) -> Self:
        return cls(type=ActionType.WRITE, path_or_command=path, content=content)

    @classmethod
    def delete(cls, path: str) -> Self:
        return cls(type=ActionType.DELETE, path_or_command=path)

    @classmethod
    def command(cls, command: str) -> Self:
        return cls(type=ActionType.COMMAND, path_or_command=command)

    @classmethod
    def network(cls, url: str) -> Self:
        return cls(type=ActionType.NETWORK, path_or_command=url)

    @classmethod
    def git_push(cls, target: str) -> Self:
        return cls(type=ActionType.GIT_PUSH, path_or_command=target)


class Feedback(DomainModel):
    id: str = Field(default_factory=_new_id)
    iteration_id: str | None = None
    kind: FeedbackKind
    exit_code: int | None = None
    summary: str = ""
    raw_log_ref: str | None = None


class Approval(DomainModel):
    id: str = Field(default_factory=_new_id)
    action_id: str
    reason: str = Field(min_length=1)
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_at: datetime | None = None

    @model_validator(mode="after")
    def decision_and_time_agree(self) -> Self:
        if self.decision is ApprovalDecision.PENDING and self.decided_at is not None:
            raise ValueError("pending approvals cannot have a decision time")
        if self.decision is not ApprovalDecision.PENDING and self.decided_at is None:
            raise ValueError("decided approvals require a decision time")
        return self


class IterationRecord(DomainModel):
    id: str = Field(default_factory=_new_id)
    task_id: str
    number: int = Field(ge=1)
    action_summary: str = ""
    workspace_fingerprint: str
    result_code: int | None = None
    feedback: Feedback | None = None
    progressed: bool = False
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
