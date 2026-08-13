import shutil
import subprocess
from pathlib import Path

import pytest


def test_async_planning_controls_approval_and_polling() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for the WebUI state behavior test")
    root = Path(__file__).parents[2]

    result = subprocess.run(
        [node, str(root / "tests" / "js" / "task-state.test.mjs")],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
