from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from feedbackloop.models import Action, ActionRisk, ActionType
from feedbackloop.security import is_sensitive_path
from feedbackloop.workspace import Workspace, WorkspaceError


class DecisionKind(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    kind: DecisionKind
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("policy decisions require a reason")


class PolicyEngine:
    def __init__(
        self,
        declared_commands: Iterable[str] = (),
        allowed_paths: Iterable[str] = (),
        unsupported_actions: Iterable[ActionType] = (),
        undeclared_commands_require_approval: bool = True,
    ) -> None:
        self._declared_commands = frozenset(declared_commands)
        self._allowed_paths = frozenset(allowed_paths)
        self._unsupported_actions = frozenset(unsupported_actions)
        self._undeclared_commands_require_approval = undeclared_commands_require_approval

    def check(self, action: Action, workspace: Workspace) -> PolicyDecision:
        if action.type in self._unsupported_actions:
            return PolicyDecision(
                DecisionKind.DENY, "action is not supported by the configured executor"
            )
        if action.type in {ActionType.READ, ActionType.WRITE, ActionType.DELETE}:
            return self._check_file_action(action, workspace)
        if action.type is ActionType.NETWORK:
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL, "network access requires approval"
            )
        if action.type is ActionType.GIT_PUSH:
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL, "Git push requires approval"
            )
        if action.type is ActionType.COMMAND:
            return self._check_command(action)
        return PolicyDecision(
            DecisionKind.REQUIRE_APPROVAL, "unrecognized action requires approval"
        )

    def _check_file_action(
        self, action: Action, workspace: Workspace
    ) -> PolicyDecision:
        try:
            resolved = workspace.resolve_child(action.path_or_command)
            relative = resolved.relative_to(workspace.resolve_repo())
        except WorkspaceError as error:
            return PolicyDecision(DecisionKind.DENY, str(error))

        if is_sensitive_path(relative):
            return PolicyDecision(
                DecisionKind.DENY, "access to sensitive files is denied"
            )
        if self._allowed_paths and not _in_plan_scope(relative, self._allowed_paths):
            return PolicyDecision(
                DecisionKind.DENY, "file action is outside the approved plan scope"
            )
        if action.type is ActionType.DELETE:
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL, "file deletion requires approval"
            )
        if action.risk is ActionRisk.DANGEROUS:
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL,
                "action marked dangerous requires approval",
            )
        return PolicyDecision(
            DecisionKind.ALLOW, "safe repository file action is allowed"
        )

    def _check_command(self, action: Action) -> PolicyDecision:
        command = action.path_or_command
        if _contains_shell_chaining(command):
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL, "shell chaining requires approval"
            )
        if command not in self._declared_commands:
            if not self._undeclared_commands_require_approval:
                return PolicyDecision(
                    DecisionKind.DENY, "undeclared command is not supported"
                )
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL, "undeclared command requires approval"
            )
        if action.risk is ActionRisk.DANGEROUS:
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL,
                "action marked dangerous requires approval",
            )
        return PolicyDecision(DecisionKind.ALLOW, "declared command is allowed")


def _contains_shell_chaining(command: str) -> bool:
    return any(token in command for token in ("&", "|", ";", "\n", "\r"))


def _in_plan_scope(relative: Path, allowed_paths: frozenset[str]) -> bool:
    return "**" in allowed_paths or relative.as_posix() in allowed_paths
