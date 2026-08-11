from pathlib import Path

import yaml


def test_github_workflow_runs_tests_demo_and_container_build():
    root = Path(__file__).parents[2]
    workflow = yaml.load(
        (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert workflow["name"] == "CI"
    assert set(workflow["on"]) == {"push", "pull_request"}
    assert set(workflow["jobs"]) == {"quality"}
    job = workflow["jobs"]["quality"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["steps"] == [
        {"uses": "actions/checkout@v4"},
        {
            "uses": "actions/setup-python@v5",
            "with": {"python-version": "3.12"},
        },
        {"run": 'python -m pip install ".[test]"'},
        {"run": "python -m pytest -q"},
        {"run": "python -m demo.scenario"},
        {"run": "docker build -t feedbackloop-demo ."},
    ]
