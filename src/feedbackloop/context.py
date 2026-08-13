from __future__ import annotations

from datetime import datetime
from pydantic import Field

from feedbackloop.feedback import redact_and_truncate
from feedbackloop.models import DomainModel, IterationRecord, Task
from feedbackloop.security import is_sensitive_path


class Plan(DomainModel):
    summary: str = Field(min_length=1)
    files: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    expected_behavior: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    validation_commands: tuple[str, ...] = ()
    potential_dangerous_actions: tuple[str, ...] = ()
    estimated_iterations: int = Field(default=1, ge=1, le=5)
    approved_at: datetime | None = None


class FileSummary(DomainModel):
    path: str = Field(min_length=1)
    summary: str = ""


class AgentContext(DomainModel):
    task_request: str
    plan_summary: str
    recent_iterations: tuple[IterationRecord, ...] = ()
    files: tuple[FileSummary, ...] = ()


class ContextBuilder:
    def __init__(
        self,
        *,
        max_recent_iterations: int = 3,
        max_file_summary_chars: int = 2_000,
        max_task_request_chars: int = 4_000,
        max_plan_summary_chars: int = 4_000,
        max_files: int = 20,
        max_total_file_summary_chars: int = 10_000,
    ) -> None:
        if max_recent_iterations < 0:
            raise ValueError("max_recent_iterations must not be negative")
        if max_file_summary_chars < 1:
            raise ValueError("max_file_summary_chars must be positive")
        if min(
            max_task_request_chars,
            max_plan_summary_chars,
            max_files,
            max_total_file_summary_chars,
        ) < 1:
            raise ValueError("context budgets must be positive")
        self.max_recent_iterations = max_recent_iterations
        self.max_file_summary_chars = max_file_summary_chars
        self.max_task_request_chars = max_task_request_chars
        self.max_plan_summary_chars = max_plan_summary_chars
        self.max_files = max_files
        self.max_total_file_summary_chars = max_total_file_summary_chars

    def build(
        self,
        task: Task,
        plan: Plan,
        recent: list[IterationRecord],
        files: list[FileSummary],
    ) -> AgentContext:
        if self.max_recent_iterations:
            bounded_recent = tuple(recent[-self.max_recent_iterations :])
        else:
            bounded_recent = ()
        bounded_file_list: list[FileSummary] = []
        remaining = self.max_total_file_summary_chars
        for file in files:
            if is_sensitive_path(file.path) or len(bounded_file_list) >= self.max_files:
                continue
            limit = min(self.max_file_summary_chars, remaining)
            if limit < 1:
                break
            summary = redact_and_truncate(file.summary, limit)
            bounded_file_list.append(FileSummary(path=file.path, summary=summary))
            remaining -= len(summary)
        return AgentContext(
            task_request=redact_and_truncate(
                task.request, self.max_task_request_chars
            ),
            plan_summary=redact_and_truncate(
                plan.summary, self.max_plan_summary_chars
            ),
            recent_iterations=bounded_recent,
            files=tuple(bounded_file_list),
        )
