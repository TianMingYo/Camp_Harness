from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Iterable, Sequence

from feedbackloop.models import CommandResult, ValidationCommand


class ValidationDetector:
    @staticmethod
    def detect(repo_root: Path) -> list[ValidationCommand]:
        root = Path(repo_root)
        commands: list[ValidationCommand] = []

        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            if "pytest" in text or "[tool.pytest" in text:
                commands.append(
                    ValidationCommand(kind="test", executable="python", args=("-m", "pytest", "-q"))
                )

        package_json = root / "package.json"
        if package_json.is_file():
            try:
                package = json.loads(package_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                package = {}
            if isinstance(package.get("scripts"), dict) and package["scripts"].get("test"):
                commands.append(ValidationCommand(kind="test", executable="npm", args=("test",)))

        if (root / "Cargo.toml").is_file():
            commands.append(ValidationCommand(kind="test", executable="cargo", args=("test",)))

        return commands

    @staticmethod
    def apply_overrides(
        detected: Iterable[ValidationCommand],
        overrides: Sequence[ValidationCommand] | None,
    ) -> list[ValidationCommand]:
        if overrides is None:
            return list(detected)
        return list(overrides)


def _bounded(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = "[truncated]"
    if limit <= len(suffix):
        return suffix[:limit]
    return text[: limit - len(suffix)] + suffix


class CommandRunner:
    def __init__(self, *, max_output_chars: int = 64_000) -> None:
        if max_output_chars < 1:
            raise ValueError("max_output_chars must be positive")
        self.max_output_chars = max_output_chars

    def run(self, command: ValidationCommand, cwd: Path) -> CommandResult:
        started = time.monotonic()
        argv = [command.executable, *command.args]
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(Path(cwd)),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=command.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return CommandResult(
                    kind=command.kind,
                    stdout=_bounded(stdout or "", self.max_output_chars),
                    stderr=_bounded(stderr or "", self.max_output_chars),
                    timed_out=True,
                    duration_seconds=max(0.0, time.monotonic() - started),
                    error="timeout",
                )
        except OSError as error:
            return CommandResult(
                kind=command.kind,
                stdout="",
                stderr="",
                duration_seconds=max(0.0, time.monotonic() - started),
                error=str(error),
            )

        return CommandResult(
            kind=command.kind,
            exit_code=process.returncode,
            stdout=_bounded(stdout or "", self.max_output_chars),
            stderr=_bounded(stderr or "", self.max_output_chars),
            duration_seconds=max(0.0, time.monotonic() - started),
        )
