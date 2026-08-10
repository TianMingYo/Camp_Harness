from __future__ import annotations

from pathlib import Path

from feedbackloop.context import FileSummary
from feedbackloop.models import Action, ActionType, CommandResult, ValidationCommand
from feedbackloop.validation import CommandRunner
from feedbackloop.workspace import Workspace, WorkspaceError


def command_text(command: ValidationCommand) -> str:
    return " ".join((command.executable, *command.args))


def _is_sensitive(relative: Path) -> bool:
    sensitive_names = {
        ".aws",
        ".dockerconfigjson",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "credentials",
        "credentials.json",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
    for part in relative.parts:
        lowered = part.casefold()
        if (
            lowered == ".git"
            or lowered == ".env"
            or lowered.startswith(".env.")
            or lowered in sensitive_names
            or lowered.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"))
        ):
            return True
    return False


class LocalExecutor:
    def __init__(
        self,
        workspace: Workspace,
        *,
        validation_commands: tuple[ValidationCommand, ...] = (),
        summary_paths: tuple[str, ...] = (),
        runner: CommandRunner | None = None,
        max_file_summary_chars: int = 4_000,
    ) -> None:
        self.workspace = workspace
        self.runner = runner or CommandRunner()
        self.max_file_summary_chars = max_file_summary_chars
        self.summary_paths = tuple(summary_paths)
        self._declared_commands = {
            command_text(command): command for command in validation_commands
        }

    def apply(self, action: Action) -> None:
        if action.type is ActionType.WRITE:
            target = self.workspace.resolve_child(action.path_or_command)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(action.content or "", encoding="utf-8")
            return
        if action.type is ActionType.READ:
            self.workspace.resolve_child(action.path_or_command).read_bytes()
            return
        if action.type is ActionType.DELETE:
            self.workspace.resolve_child(action.path_or_command).unlink()
            return
        if action.type is ActionType.COMMAND:
            command = self._declared_commands.get(action.path_or_command)
            if command is None:
                raise ValueError("command was not declared by the approved plan")
            result = self.validate(command)
            if result.timed_out or result.error or result.exit_code != 0:
                raise RuntimeError("approved command failed")
            return
        raise ValueError(f"unsupported local action: {action.type.value}")

    def validate(self, command: ValidationCommand) -> CommandResult:
        return self.runner.run(command, self.workspace.resolve_repo())

    def fingerprint(self) -> str:
        return self.workspace.fingerprint()

    def file_summaries(self) -> list[FileSummary]:
        root = self.workspace.resolve_repo()
        summaries: list[FileSummary] = []
        for relative_text in self.summary_paths:
            if relative_text in {"", "**"}:
                continue
            relative = Path(relative_text)
            if _is_sensitive(relative):
                continue
            try:
                resolved = self.workspace.resolve_child(relative.as_posix())
            except WorkspaceError:
                continue
            if not resolved.is_file():
                continue
            with resolved.open("rb") as source:
                raw = source.read(self.max_file_summary_chars * 4)
            content = raw.decode("utf-8", errors="replace")
            summaries.append(
                FileSummary(
                    path=relative.as_posix(),
                    summary=content[: self.max_file_summary_chars],
                )
            )
        return summaries
