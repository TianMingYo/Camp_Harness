import sqlite3
from pathlib import Path

import pytest

from feedbackloop.context import Plan
from feedbackloop.models import Feedback, FeedbackKind, IterationRecord, Task
from feedbackloop.store import Store


def task() -> Task:
    return Task.create(repo_root="/repo", request="feature")


def iteration(task_id: str) -> IterationRecord:
    return IterationRecord(
        id="iteration-1", task_id=task_id, number=1, workspace_fingerprint="abc"
    )


def test_store_round_trips_task_plan_iteration_and_feedback(tmp_path: Path):
    store = Store(tmp_path / "tasks.sqlite3")
    created = task()
    store.create_task(created)
    store.save_plan(created.id, Plan(summary="implement feature"))
    store.save_iteration(iteration(created.id))
    store.save_feedback(
        Feedback(
            id="feedback-1",
            iteration_id="iteration-1",
            kind=FeedbackKind.TEST_FAILURE,
            summary="one failed",
        )
    )

    assert store.get_task(created.id) == created
    assert store.get_plan(created.id).summary == "implement feature"
    assert store.get_iteration("iteration-1").task_id == created.id
    assert store.get_feedback("iteration-1").kind is FeedbackKind.TEST_FAILURE


def test_store_rejects_iteration_for_missing_task(tmp_path: Path):
    store = Store(tmp_path / "tasks.sqlite3")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_iteration(iteration("missing"))
    assert store.get_iteration("iteration-1") is None


def test_feedback_and_audit_payloads_are_redacted(tmp_path: Path):
    store = Store(tmp_path / "tasks.sqlite3")
    created = task()
    store.create_task(created)
    store.save_iteration(iteration(created.id))
    store.save_feedback(
        Feedback(
            iteration_id="iteration-1",
            kind=FeedbackKind.COMMAND_ERROR,
            summary="Authorization: Bearer secret-token",
        )
    )
    store.append_audit_event(created.id, "provider_error", {"API_KEY": "secret-value"})

    raw = (tmp_path / "tasks.sqlite3").read_bytes()
    assert b"secret-token" not in raw
    assert b"secret-value" not in raw
    assert "[REDACTED]" in store.get_feedback("iteration-1").summary


def test_iteration_number_is_unique_per_task(tmp_path: Path):
    store = Store(tmp_path / "tasks.sqlite3")
    created = task()
    store.create_task(created)
    store.save_iteration(iteration(created.id))
    duplicate = iteration(created.id).model_copy(update={"id": "iteration-2"})
    with pytest.raises(sqlite3.IntegrityError):
        store.save_iteration(duplicate)
