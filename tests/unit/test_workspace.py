from pathlib import Path
import subprocess

import pytest

from feedbackloop.workspace import (
    InvalidRepositoryError,
    PathBoundaryError,
    Workspace,
)


def git_workspace(root: Path) -> Workspace:
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return Workspace(root)


def test_resolve_repo_accepts_actual_git_root(tmp_path: Path) -> None:
    workspace = git_workspace(tmp_path)

    assert workspace.resolve_repo() == tmp_path.resolve()


def test_resolve_repo_rejects_fabricated_git_marker(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    with pytest.raises(InvalidRepositoryError, match="Git"):
        Workspace(tmp_path).resolve_repo()


def test_resolve_repo_rejects_directory_without_git_marker(tmp_path: Path) -> None:
    with pytest.raises(InvalidRepositoryError, match="Git"):
        Workspace(tmp_path).resolve_repo()


def test_resolve_child_normalizes_a_path_that_remains_in_repo(tmp_path: Path) -> None:
    workspace = git_workspace(tmp_path)
    expected = tmp_path / "src" / "module.py"

    assert workspace.resolve_child("src/../src/module.py") == expected.resolve()


@pytest.mark.parametrize("candidate", ["../outside.txt", "../../outside.txt"])
def test_resolve_child_rejects_parent_escape(tmp_path: Path, candidate: str) -> None:
    workspace = git_workspace(tmp_path)

    with pytest.raises(PathBoundaryError, match="outside"):
        workspace.resolve_child(candidate)


def test_resolve_child_rejects_absolute_outside_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    workspace = git_workspace(repo)

    with pytest.raises(PathBoundaryError, match="outside"):
        workspace.resolve_child(str(tmp_path / "outside.txt"))


def test_resolve_child_rejects_symlink_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    workspace = git_workspace(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = repo / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    with pytest.raises(PathBoundaryError, match="outside"):
        workspace.resolve_child("linked/secret.txt")


def test_fingerprint_is_independent_of_file_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_workspace = git_workspace(first)
    second_workspace = git_workspace(second)
    (first / "b.txt").write_text("bravo", encoding="utf-8")
    (first / "a.txt").write_text("alpha", encoding="utf-8")
    (second / "a.txt").write_text("alpha", encoding="utf-8")
    (second / "b.txt").write_text("bravo", encoding="utf-8")

    assert first_workspace.fingerprint() == second_workspace.fingerprint()


def test_fingerprint_changes_when_tracked_content_changes(tmp_path: Path) -> None:
    workspace = git_workspace(tmp_path)
    source = tmp_path / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    before = workspace.fingerprint()

    source.write_text("value = 2\n", encoding="utf-8")

    assert workspace.fingerprint() != before


def test_fingerprint_excludes_git_internals(tmp_path: Path) -> None:
    workspace = git_workspace(tmp_path)
    source = tmp_path / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    before = workspace.fingerprint()

    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    assert workspace.fingerprint() == before
