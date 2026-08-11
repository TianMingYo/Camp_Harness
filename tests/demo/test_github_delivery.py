from pathlib import Path

import yaml


def test_github_workflow_runs_tests_demo_and_container_build():
    root = Path(__file__).parents[2]
    workflow = yaml.load(
        (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert set(workflow["on"]) == {"push", "pull_request"}
    job = workflow["jobs"]["quality"]
    assert job["runs-on"] == "ubuntu-latest"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert 'python -m pip install ".[test]"' in commands
    assert "python -m pytest -q" in commands
    assert "python -m demo.scenario" in commands
    assert "docker build -t feedbackloop-demo ." in commands
