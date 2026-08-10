from pathlib import Path

from feedbackloop.models import Action
from feedbackloop.policy import DecisionKind, PolicyEngine
from feedbackloop.workspace import Workspace
from demo.scenario import run_demo


def test_mechanism_demo_blocks_dangerous_delete(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    decision = PolicyEngine().check(Action.delete("important.py"), Workspace(tmp_path))
    assert decision.kind is DecisionKind.REQUIRE_APPROVAL


def test_demo_contains_feedback_correction_and_policy_block():
    result = run_demo()
    assert result.corrected_after_feedback is True
    assert result.policy_blocked is True
    assert result.used_network is False


def test_packaging_metadata_contains_required_entrypoints():
    root = Path(__file__).parents[2]
    assert "feedbackloop.api:demo_app" in (root / "Dockerfile").read_text(encoding="utf-8")
    assert "unit-test:" in (root / ".gitlab-ci.yml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    for heading in ("Installation", "Local WebUI", "Provider configuration", "Safety limits", "Offline demo"):
        assert heading in readme
