import subprocess
from pathlib import Path


def init_git_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return root
