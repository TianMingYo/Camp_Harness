from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from feedbackloop.models import Action, ActionRisk, ActionType
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
    def __init__(self, declared_commands: Iterable[str] = ()) -> None:
        self._declared_commands = frozenset(declared_commands)

    def check(self, action: Action, workspace: Workspace) -> PolicyDecision:
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

        if _is_sensitive(relative):
            return PolicyDecision(
                DecisionKind.DENY, "access to sensitive files is denied"
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
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL, "undeclared command requires approval"
            )
        if action.risk is ActionRisk.DANGEROUS:
            return PolicyDecision(
                DecisionKind.REQUIRE_APPROVAL,
                "action marked dangerous requires approval",
            )
        return PolicyDecision(DecisionKind.ALLOW, "declared command is allowed")


def _is_sensitive(relative: Path) -> bool:
    lowered_parts = tuple(part.casefold() for part in relative.parts)
    sensitive_names = {
        ".netrc",
        "credentials",
        "id_dsa",
        "id_ed25519",
        "id_ecdsa",
        "id_rsa",
    }
    return any(
        part == ".git"
        or part == ".env"
        or part.startswith(".env.")
        or part in sensitive_names
        for part in lowered_parts
    )


def _contains_shell_chaining(command: str) -> bool:
    return any(token in command for token in ("&", "|", ";", "\n", "\r"))
