from pathlib import Path

from feedbackloop.models import ValidationCommand
from feedbackloop.validation import ValidationDetector


def test_detects_pytest_from_pyproject(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8"
    )

    commands = ValidationDetector.detect(tmp_path)

    assert any(command.kind == "test" for command in commands)
    assert any(command.args[:2] == ("-m", "pytest") for command in commands)


def test_detects_node_and_rust_markers(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")
    assert any(command.executable == "npm" for command in ValidationDetector.detect(tmp_path))

    (tmp_path / "Cargo.toml").write_text("[package]\nname='demo'\n", encoding="utf-8")
    assert any(command.executable == "cargo" for command in ValidationDetector.detect(tmp_path))


def test_overrides_replace_only_commands_of_the_same_kind(tmp_path: Path):
    detected = [
        ValidationCommand(kind="test", executable="pytest"),
        ValidationCommand(kind="lint", executable="ruff", args=("check", ".")),
    ]
    overrides = [
        ValidationCommand(
            kind="test", executable="python", args=("-m", "pytest", "focused")
        )
    ]

    assert ValidationDetector.apply_overrides(detected, overrides) == [
        overrides[0],
        detected[1],
    ]


def test_empty_repo_has_no_implicit_command(tmp_path: Path):
    assert ValidationDetector.detect(tmp_path) == []
