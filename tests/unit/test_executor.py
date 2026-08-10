import sys
from pathlib import Path

from feedbackloop.executor import LocalExecutor
from feedbackloop.models import Action, ValidationCommand
from feedbackloop.workspace import Workspace


def test_local_executor_applies_bounded_file_edits_and_runs_validation(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    executor = LocalExecutor(Workspace(repo))

    executor.apply(Action.write("src/greeting.py", "GREETING = 'hello'\n"))

    assert (repo / "src" / "greeting.py").read_text(encoding="utf-8") == (
        "GREETING = 'hello'\n"
    )
    assert executor.file_summaries()[0].path == "src/greeting.py"
    result = executor.validate(
        ValidationCommand(
            kind="test",
            executable=sys.executable,
            args=("-c", "from pathlib import Path; assert Path('src/greeting.py').exists()"),
        )
    )
    assert result.exit_code == 0


def test_local_executor_never_reads_sensitive_file_summaries(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".env").write_text("API_KEY=must-not-be-read", encoding="utf-8")
    (repo / "visible.txt").write_text("public", encoding="utf-8")

    summaries = LocalExecutor(Workspace(repo)).file_summaries()

    assert [item.path for item in summaries] == ["visible.txt"]
