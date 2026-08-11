import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_render_blueprint_deploys_safe_feature_branch_after_checks():
    blueprint = yaml.load(
        (ROOT / "render.yaml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert blueprint == {
        "services": [
            {
                "type": "web",
                "name": "feedbackloop-harness-demo",
                "runtime": "docker",
                "plan": "free",
                "region": "singapore",
                "repo": "https://github.com/TianMingYo/Camp_Harness",
                "branch": "feature/feedback-loop-harness",
                "dockerfilePath": "./Dockerfile",
                "dockerContext": ".",
                "healthCheckPath": "/",
                "autoDeployTrigger": "checksPass",
            }
        ]
    }


def test_docker_image_links_source_and_honors_render_port():
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    assert (
        'LABEL org.opencontainers.image.source="https://github.com/TianMingYo/Camp_Harness"'
        in lines
    )
    command_line = next(line for line in lines if line.startswith("CMD "))
    assert json.loads(command_line.removeprefix("CMD ")) == [
        "sh",
        "-c",
        'exec python -m uvicorn feedbackloop.api:demo_app --host 0.0.0.0 --port "${PORT:-8000}"',
    ]
