from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class WorkspaceError(ValueError):
    """Base error for invalid workspace operations."""


class InvalidRepositoryError(WorkspaceError):
    """Raised when a workspace root is not a Git repository."""


class PathBoundaryError(WorkspaceError):
    """Raised when a path resolves outside the repository."""


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path

    def resolve_repo(self) -> Path:
        root = self.root.expanduser().resolve()
        if not root.is_dir():
            raise InvalidRepositoryError(f"repository root is not a directory: {root}")

        git_marker = root / ".git"
        if not (git_marker.is_dir() or git_marker.is_file()):
            raise InvalidRepositoryError(f"Git repository marker not found: {root}")
        return root

    def resolve_child(self, candidate: str) -> Path:
        root = self.resolve_repo()
        path = Path(candidate).expanduser()
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise PathBoundaryError(
                f"path resolves outside repository: {candidate}"
            ) from error
        return resolved

    def fingerprint(self) -> str:
        root = self.resolve_repo()
        digest = sha256()
        files = sorted(
            (
                path
                for path in root.rglob("*")
                if path.relative_to(root).parts[0] != ".git" and path.is_file()
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )

        for path in files:
            relative = path.relative_to(root).as_posix().encode("utf-8")
            resolved = self.resolve_child(str(path.relative_to(root)))
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            with resolved.open("rb") as source:
                while chunk := source.read(64 * 1024):
                    digest.update(len(chunk).to_bytes(8, "big"))
                    digest.update(chunk)
            digest.update((0).to_bytes(8, "big"))

        return digest.hexdigest()
