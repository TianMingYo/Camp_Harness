# GitHub Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add course-compliant GitHub Actions validation, publish the feature branch to `TianMingYo/Camp_Harness`, and open a Pull Request targeting `main` without touching the dirty main worktree.

**Architecture:** A parsed YAML contract test defines the required GitHub Actions behavior before the workflow exists. The workflow runs the same package tests and deterministic demo already used locally, then builds the existing Dockerfile. Publishing uses the existing named feature branch and normal Git push/PR APIs; authentication failure stops without rewriting history.

**Tech Stack:** GitHub Actions, YAML, Python 3.12, PyYAML test parser, pytest, Docker, Git.

## Global Constraints

- Keep `.gitlab-ci.yml` and its `unit-test` job because the final course checklist requires it.
- GitHub Actions must run on every push and Pull Request.
- Container distribution requires CI to build the Docker image.
- Never commit credentials, print tokens, force-push, merge the Pull Request, or modify the main worktree's existing changes.
- Every configuration behavior follows RED -> GREEN -> REFACTOR and records evidence in `AGENT_LOG.md`.
- The PR description identifies subagent work, controller corrections, TDD evidence, verification results, and external gates.

---

### Task 1: GitHub Actions Contract

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/demo/test_github_delivery.py`
- Modify: `pyproject.toml`
- Modify: `AGENT_LOG.md`

**Interfaces:**
- Consumes: `python -m pytest -q`, `python -m demo.scenario`, and the repository `Dockerfile`.
- Produces: a GitHub Actions workflow named `CI` with one `quality` job that tests and builds the image.

- [ ] **Step 1: Write the failing parsed-workflow test**

```python
from pathlib import Path

import yaml


def test_github_workflow_runs_tests_demo_and_container_build():
    root = Path(__file__).parents[2]
    workflow = yaml.load(
        (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert set(workflow["on"]) == {"push", "pull_request"}
    job = workflow["jobs"]["quality"]
    assert job["runs-on"] == "ubuntu-latest"
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert 'python -m pip install ".[test]"' in commands
    assert "python -m pytest -q" in commands
    assert "python -m demo.scenario" in commands
    assert "docker build -t feedbackloop-demo ." in commands
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_github_delivery.py -q`

Expected: FAIL because `.github/workflows/ci.yml` does not exist.

- [ ] **Step 3: Add the YAML parser test dependency**

Change the test extra in `pyproject.toml` to:

```toml
[project.optional-dependencies]
test = ["pytest>=8,<9", "pyyaml>=6,<7"]
```

- [ ] **Step 4: Add the minimal workflow**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install ".[test]"
      - run: python -m pytest -q
      - run: python -m demo.scenario
      - run: docker build -t feedbackloop-demo .
```

- [ ] **Step 5: Verify GREEN and full regression**

Run:

```powershell
C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_github_delivery.py -q
C:\Users\13900\anaconda3\python.exe -m pytest -q
ruff check src tests demo
C:\Users\13900\anaconda3\python.exe -m demo.scenario
git diff --check
```

Expected: focused test passes, complete suite passes with only the documented Windows symlink skip and TestClient warning, Ruff passes, demo reports `final_state: succeeded`, and diff check exits zero.

- [ ] **Step 6: Record evidence and commit**

Add the exact RED/GREEN output summary to `AGENT_LOG.md`, then run:

```powershell
git add .github/workflows/ci.yml tests/demo/test_github_delivery.py pyproject.toml AGENT_LOG.md docs/superpowers/plans/2026-08-11-github-delivery.md
git commit -m "ci: add GitHub delivery workflow"
```

---

### Task 2: Push Branch And Open Pull Request

**Files:**
- Modify: Git remote configuration only; no source file changes are expected.

**Interfaces:**
- Consumes: local branch `feature/feedback-loop-harness`, base branch `main`, remote URL `https://github.com/TianMingYo/Camp_Harness.git`.
- Produces: remote feature branch, Pull Request URL, and observable GitHub Actions checks.

- [ ] **Step 1: Verify the remote before mutation**

Run: `git ls-remote https://github.com/TianMingYo/Camp_Harness.git`

Expected: the repository is reachable. Authentication failure or repository-not-found stops this task.

- [ ] **Step 2: Configure the remote without overwriting another URL**

Run:

```powershell
git remote get-url origin
```

If `origin` is absent, run:

```powershell
git remote add origin https://github.com/TianMingYo/Camp_Harness.git
```

If it exists with a different URL, stop and request direction rather than replacing it.

- [ ] **Step 3: Push the named feature branch**

Run: `git push -u origin feature/feedback-loop-harness`

Expected: normal push succeeds without force and sets the upstream.

- [ ] **Step 4: Create the Pull Request**

Use GitHub CLI when authenticated:

```powershell
gh pr create --base main --head feature/feedback-loop-harness --title "Build deterministic coding-agent feedback harness" --body-file PR_BODY.md
```

The temporary PR body must state:

```markdown
## Summary
- implement the project-owned deterministic feedback loop and policy boundary
- add OpenAI-compatible structured planning with explicit plan approval
- add local WebUI, mock mechanism demo, GitHub/GitLab CI, and Docker packaging

## Process
- Superpowers seven-step workflow recorded in AGENT_LOG.md
- subagents performed independent read-only reviews; controller applied and verified fixes
- every behavior change followed focused RED -> GREEN -> REFACTOR evidence

## Verification
- complete pytest suite passes with the documented Windows symlink skip
- Ruff, compileall, mock demo, secret scan, and Dockerfile contract pass locally

## External gates
- public WebUI deployment URL remains to be supplied
- REFLECTION.md must be completed by the student
```

If `gh` is unavailable or unauthenticated, stop after push and provide GitHub's compare URL; do not fabricate a PR.

- [ ] **Step 5: Check GitHub Actions**

Run:

```powershell
$prNumber = gh pr view --json number --jq .number
gh pr checks $prNumber --watch
```

Expected: the `quality` job finishes successfully. If GitHub reports a real failure, inspect its logs and return to a focused RED/GREEN fix; if authentication prevents inspection, report that external gate.

- [ ] **Step 6: Preserve the branch and worktree**

Run:

```powershell
git status --short
git log -3 --oneline
```

Expected: the feature worktree is clean, the branch remains available for PR feedback, and `main` has not been merged or modified.

## Plan Self-Review

- Spec coverage: Task 1 covers every GitHub Actions behavior and retains the required GitLab job; Task 2 covers remote validation, normal push, PR creation, CI observation, and non-destructive failure handling.
- Placeholder scan: no unresolved placeholders, deferred implementation steps, or ambiguous error behavior remain.
- Interface consistency: workflow job `quality`, branch `feature/feedback-loop-harness`, base `main`, and remote URL match the approved design and commands throughout.
