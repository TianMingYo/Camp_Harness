from pathlib import Path

import pytest

from feedbackloop.models import Action, ActionType
from feedbackloop.policy import DecisionKind, PolicyEngine
from feedbackloop.workspace import Workspace
from tests.helpers import init_git_repo


def git_workspace(root: Path) -> Workspace:
    init_git_repo(root)
    return Workspace(root)


@pytest.mark.parametrize(
    "action",
    [
        Action.read("src/module.py"),
        Action.write("src/module.py", "value = 1\n"),
    ],
)
def test_policy_allows_safe_in_repo_file_actions(tmp_path: Path, action: Action) -> None:
    decision = PolicyEngine().check(action, git_workspace(tmp_path))

    assert decision.kind is DecisionKind.ALLOW
    assert decision.reason


@pytest.mark.parametrize(
    "action",
    [
        Action.delete("inside.txt"),
        Action.network("https://example.test"),
        Action.git_push("origin/main"),
    ],
)
def test_policy_requires_approval_for_intrinsically_risky_actions(
    tmp_path: Path, action: Action
) -> None:
    decision = PolicyEngine().check(action, git_workspace(tmp_path))

    assert decision.kind is DecisionKind.REQUIRE_APPROVAL
    assert decision.reason


@pytest.mark.parametrize(
    "action",
    [
        Action.read(".env"),
        Action.write(".env.local", "TOKEN=secret\n"),
        Action.delete(".git/config"),
    ],
)
def test_policy_denies_sensitive_file_access(tmp_path: Path, action: Action) -> None:
    decision = PolicyEngine().check(action, git_workspace(tmp_path))

    assert decision.kind is DecisionKind.DENY
    assert decision.reason


def test_sensitive_delete_denial_wins_over_delete_approval(tmp_path: Path) -> None:
    decision = PolicyEngine().check(Action.delete(".env"), git_workspace(tmp_path))

    assert decision.kind is DecisionKind.DENY


@pytest.mark.parametrize(
    "action",
    [
        Action.read("../secret.txt"),
        Action.write("../secret.txt", "data"),
        Action.delete("../secret.txt"),
    ],
)
def test_policy_denies_escaped_file_paths(tmp_path: Path, action: Action) -> None:
    decision = PolicyEngine().check(action, git_workspace(tmp_path))

    assert decision.kind is DecisionKind.DENY
    assert decision.reason


def test_policy_denies_file_outside_approved_plan_scope(tmp_path: Path) -> None:
    policy = PolicyEngine(allowed_paths={"src/allowed.py"})

    decision = policy.check(Action.write("src/other.py", "value = 1\n"), git_workspace(tmp_path))

    assert decision.kind is DecisionKind.DENY
    assert "plan scope" in decision.reason


def test_policy_allows_an_exact_declared_command(tmp_path: Path) -> None:
    policy = PolicyEngine(declared_commands={"python -m pytest -q"})

    decision = policy.check(
        Action.command("python -m pytest -q"), git_workspace(tmp_path)
    )

    assert decision.kind is DecisionKind.ALLOW
    assert decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q; whoami",
        "python -m pytest -q && whoami",
        "python -m pytest -q & whoami",
        "python -m pytest -q | tee results.txt",
    ],
)
def test_policy_requires_approval_for_shell_chaining(
    tmp_path: Path, command: str
) -> None:
    policy = PolicyEngine(declared_commands={command})

    decision = policy.check(Action.command(command), git_workspace(tmp_path))

    assert decision.kind is DecisionKind.REQUIRE_APPROVAL
    assert decision.reason


def test_policy_requires_approval_for_undeclared_command(tmp_path: Path) -> None:
    decision = PolicyEngine().check(
        Action.command("python -m pytest -q"), git_workspace(tmp_path)
    )

    assert decision.kind is DecisionKind.REQUIRE_APPROVAL
    assert decision.reason


def test_local_policy_denies_actions_the_executor_does_not_support(tmp_path: Path) -> None:
    policy = PolicyEngine(
        unsupported_actions={ActionType.NETWORK, ActionType.GIT_PUSH},
        undeclared_commands_require_approval=False,
    )
    workspace = git_workspace(tmp_path)

    assert policy.check(Action.network("https://example.test"), workspace).kind is DecisionKind.DENY
    assert policy.check(Action.git_push("origin/main"), workspace).kind is DecisionKind.DENY
    assert policy.check(Action.command("whoami"), workspace).kind is DecisionKind.DENY
