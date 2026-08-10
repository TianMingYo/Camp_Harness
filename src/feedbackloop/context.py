from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field

from feedbackloop.feedback import redact_and_truncate
from feedbackloop.models import DomainModel, IterationRecord, Task


class Plan(DomainModel):
    summary: str = Field(min_length=1)
    files: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()


class FileSummary(DomainModel):
    path: str = Field(min_length=1)
    summary: str = ""


class AgentContext(DomainModel):
    task_request: str
    plan_summary: str
    recent_iterations: tuple[IterationRecord, ...] = ()
    files: tuple[FileSummary, ...] = ()


def _is_sensitive_path(path: str) -> bool:
    parts = tuple(part.casefold() for part in PurePosixPath(path.replace("\\", "/")).parts)
    return any(
        part == ".git"
        or part == ".env"
        or part.startswith(".env.")
        or part in {"credentials", ".netrc", "id_rsa", "id_ed25519"}
        for part in parts
    )


class ContextBuilder:
    def __init__(
        self,
        *,
        max_recent_iterations: int = 3,
        max_file_summary_chars: int = 2_000,
    ) -> None:
        if max_recent_iterations < 0:
            raise ValueError("max_recent_iterations must not be negative")
        if max_file_summary_chars < 1:
            raise ValueError("max_file_summary_chars must be positive")
        self.max_recent_iterations = max_recent_iterations
        self.max_file_summary_chars = max_file_summary_chars

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
        bounded_files = tuple(
            FileSummary(
                path=file.path,
                summary=redact_and_truncate(file.summary, self.max_file_summary_chars),
            )
            for file in files
            if not _is_sensitive_path(file.path)
        )
        return AgentContext(
            task_request=task.request,
            plan_summary=plan.summary,
            recent_iterations=bounded_recent,
            files=bounded_files,
        )
