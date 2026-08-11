from pathlib import Path

import yaml


def _workflow() -> dict:
    root = Path(__file__).parents[2]
    return yaml.load(
        (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_github_workflow_runs_quality_and_dynamic_port_smoke():
    workflow = _workflow()
    assert workflow["name"] == "CI"
    assert set(workflow["on"]) == {"push", "pull_request"}
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"quality", "publish"}

    quality = workflow["jobs"]["quality"]
    assert quality["runs-on"] == "ubuntu-latest"
    steps = quality["steps"]
    assert steps[:6] == [
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
    assert steps[6]["name"] == "Smoke dynamic-port container"
    assert steps[6]["run"].splitlines() == [
        "docker run -d --name feedbackloop-smoke -e PORT=10000 -p 10000:10000 feedbackloop-demo",
        "curl --fail --retry 20 --retry-delay 1 --retry-all-errors http://127.0.0.1:10000/demo/scenario -o /tmp/demo-scenario.json",
        "python -c 'import json; from pathlib import Path; data=json.loads(Path(\"/tmp/demo-scenario.json\").read_text()); assert data == {\"mode\": \"mock\", \"repository\": \"embedded-sample\", \"iterations\": [\"test_failure\", \"pass\"], \"approval\": \"delete_requires_approval\"}'",
    ]
    assert steps[7] == {
        "name": "Clean up smoke container",
        "if": "always()",
        "run": "docker rm -f feedbackloop-smoke || true",
    }
    branch_push = (
        "github.event_name == 'push' && "
        "github.ref == 'refs/heads/feature/feedback-loop-harness'"
    )
    assert steps[8] == {
        "name": "Save tested image",
        "if": branch_push,
        "run": "docker save feedbackloop-demo -o feedbackloop-demo.tar",
    }
    assert steps[9] == {
        "name": "Upload tested image",
        "if": branch_push,
        "uses": "actions/upload-artifact@v4",
        "with": {
            "name": "feedbackloop-demo-image",
            "path": "feedbackloop-demo.tar",
            "retention-days": "1",
        },
    }


def test_github_workflow_publishes_ghcr_only_after_push_quality():
    publish = _workflow()["jobs"]["publish"]
    assert publish["if"] == (
        "github.event_name == 'push' && "
        "github.ref == 'refs/heads/feature/feedback-loop-harness'"
    )
    assert publish["needs"] == "quality"
    assert publish["runs-on"] == "ubuntu-latest"
    assert publish["permissions"] == {"contents": "read", "packages": "write"}
    assert publish["steps"][:3] == [
        {
            "uses": "actions/download-artifact@v4",
            "with": {"name": "feedbackloop-demo-image"},
        },
        {"run": "docker load --input feedbackloop-demo.tar"},
        {
            "uses": "docker/login-action@v3",
            "with": {
                "registry": "ghcr.io",
                "username": "${{ github.actor }}",
                "password": "${{ secrets.GITHUB_TOKEN }}",
            },
        },
    ]
    assert publish["steps"][3]["name"] == "Publish tested image"
    assert publish["steps"][3]["run"].splitlines() == [
        "docker tag feedbackloop-demo ghcr.io/tianmingyo/camp_harness:${{ github.sha }}",
        "docker tag feedbackloop-demo ghcr.io/tianmingyo/camp_harness:latest",
        "docker push ghcr.io/tianmingyo/camp_harness:${{ github.sha }}",
        "docker push ghcr.io/tianmingyo/camp_harness:latest",
    ]
