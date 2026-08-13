import sys
from pathlib import Path

from feedbackloop.models import ValidationCommand
from feedbackloop.validation import CommandRunner


def test_runner_returns_structured_nonzero_result(tmp_path: Path):
    command = ValidationCommand(
        kind="test", executable=sys.executable, args=("-c", "print('out'); raise SystemExit(3)")
    )

    result = CommandRunner().run(command, tmp_path)

    assert result.exit_code == 3
    assert result.timed_out is False
    assert result.stdout.strip() == "out"
    assert result.duration_seconds >= 0


def test_runner_returns_timeout_without_hanging(tmp_path: Path):
    command = ValidationCommand(
        kind="test",
        executable=sys.executable,
        args=("-c", "import time; time.sleep(1)"),
        timeout_seconds=0.05,
    )

    result = CommandRunner().run(command, tmp_path)

    assert result.timed_out is True
    assert result.exit_code is None
    assert result.error == "timeout"


def test_runner_reports_missing_executable(tmp_path: Path):
    command = ValidationCommand(kind="test", executable="definitely-not-installed")

    result = CommandRunner().run(command, tmp_path)

    assert result.exit_code is None
    assert result.timed_out is False
    assert result.error


def test_runner_bounds_output(tmp_path: Path):
    command = ValidationCommand(
        kind="test",
        executable=sys.executable,
        args=("-c", "print('x' * 1000)")
    )

    result = CommandRunner(max_output_chars=100).run(command, tmp_path)

    assert len(result.stdout) <= 100
    assert result.stdout.endswith("[truncated]")
