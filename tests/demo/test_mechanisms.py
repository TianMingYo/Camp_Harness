from pathlib import Path

from feedbackloop.models import Action
from feedbackloop.policy import DecisionKind, PolicyEngine
from feedbackloop.workspace import Workspace


def test_mechanism_demo_blocks_dangerous_delete(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    decision = PolicyEngine().check(Action.delete("important.py"), Workspace(tmp_path))
    assert decision.kind is DecisionKind.REQUIRE_APPROVAL
