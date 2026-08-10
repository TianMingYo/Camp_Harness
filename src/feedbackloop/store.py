from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from feedbackloop.context import Plan
from feedbackloop.feedback import redact_and_truncate
from feedbackloop.models import Action, Approval, Feedback, IterationRecord, Task


def _sanitize(value: Any, key: str = "") -> Any:
    lowered = key.casefold()
    if any(marker in lowered for marker in ("key", "token", "secret", "credential")):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {name: _sanitize(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_and_truncate(value, 16_000)
    return value


def _payload(model: Any) -> str:
    value = model.model_dump(mode="json") if hasattr(model, "model_dump") else model
    return json.dumps(_sanitize(value), ensure_ascii=True, separators=(",", ":"))


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def close(self) -> None:
        """Compatibility hook; operation-scoped connections are already closed."""

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plans (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS iterations (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    number INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(task_id, number)
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    iteration_id TEXT REFERENCES iterations(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id TEXT PRIMARY KEY,
                    iteration_id TEXT NOT NULL UNIQUE REFERENCES iterations(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL UNIQUE REFERENCES actions(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def create_task(self, task: Task) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO tasks(id,payload) VALUES (?,?)", (task.id, _payload(task)))

    def update_task(self, task: Task) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET payload=? WHERE id=?", (_payload(task), task.id)
            )
            if cursor.rowcount != 1:
                raise KeyError(task.id)

    def get_task(self, task_id: str) -> Task | None:
        payload = self._one("SELECT payload FROM tasks WHERE id=?", (task_id,))
        return Task.model_validate_json(payload) if payload else None

    def save_plan(self, task_id: str, plan: Plan) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO plans(task_id,payload) VALUES (?,?) "
                "ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload",
                (task_id, _payload(plan)),
            )

    def get_plan(self, task_id: str) -> Plan | None:
        payload = self._one("SELECT payload FROM plans WHERE task_id=?", (task_id,))
        return Plan.model_validate_json(payload) if payload else None

    def save_iteration(self, iteration: IterationRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO iterations(id,task_id,number,payload) VALUES (?,?,?,?)",
                (iteration.id, iteration.task_id, iteration.number, _payload(iteration)),
            )

    def get_iteration(self, iteration_id: str) -> IterationRecord | None:
        payload = self._one("SELECT payload FROM iterations WHERE id=?", (iteration_id,))
        return IterationRecord.model_validate_json(payload) if payload else None

    def list_iterations(self, task_id: str) -> list[IterationRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM iterations WHERE task_id=? ORDER BY number", (task_id,)
            ).fetchall()
        return [IterationRecord.model_validate_json(row[0]) for row in rows]

    def save_action(self, action: Action) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO actions(id,iteration_id,payload) VALUES (?,?,?)",
                (action.id, action.iteration_id, _payload(action)),
            )

    def get_action(self, action_id: str) -> Action | None:
        payload = self._one("SELECT payload FROM actions WHERE id=?", (action_id,))
        return Action.model_validate_json(payload) if payload else None

    def save_feedback(self, feedback: Feedback) -> None:
        if feedback.iteration_id is None:
            raise ValueError("feedback requires iteration_id")
        sanitized = feedback.model_copy(
            update={"summary": redact_and_truncate(feedback.summary, 16_000)}
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO feedback(id,iteration_id,payload) VALUES (?,?,?)",
                (feedback.id, feedback.iteration_id, _payload(sanitized)),
            )

    def get_feedback(self, iteration_id: str) -> Feedback | None:
        payload = self._one("SELECT payload FROM feedback WHERE iteration_id=?", (iteration_id,))
        return Feedback.model_validate_json(payload) if payload else None

    def save_approval(self, approval: Approval) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO approvals(id,action_id,payload) VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (approval.id, approval.action_id, _payload(approval)),
            )

    def get_approval(self, action_id: str) -> Approval | None:
        payload = self._one("SELECT payload FROM approvals WHERE action_id=?", (action_id,))
        return Approval.model_validate_json(payload) if payload else None

    def get_approval_by_id(self, approval_id: str) -> Approval | None:
        payload = self._one("SELECT payload FROM approvals WHERE id=?", (approval_id,))
        return Approval.model_validate_json(payload) if payload else None

    def append_audit_event(self, task_id: str, kind: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(task_id,kind,payload) VALUES (?,?,?)",
                (task_id, kind, _payload(payload)),
            )

    def _one(self, statement: str, parameters: tuple[Any, ...]) -> str | None:
        with self._connect() as connection:
            row = connection.execute(statement, parameters).fetchone()
        return row[0] if row else None
