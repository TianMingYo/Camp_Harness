# GitHub Delivery Design

## Goal

Publish `feature/feedback-loop-harness` to `TianMingYo/Camp_Harness` through a
Pull Request while preserving the course-required commit history, Superpowers evidence,
tests, container build, and existing GitLab CI configuration.

## Repository And Branch Strategy

- Configure `origin` as `https://github.com/TianMingYo/Camp_Harness.git`.
- Push the existing `feature/feedback-loop-harness` branch without rewriting history.
- Open a Pull Request targeting `main`; do not merge it automatically.
- Leave the main worktree and its existing uncommitted files untouched.

## GitHub Actions Contract

Add `.github/workflows/ci.yml` with these observable behaviors:

- Trigger on pushes and Pull Requests.
- Run on Ubuntu with Python 3.12.
- Install the package with test dependencies.
- Run the complete pytest suite.
- Run the deterministic mock-LLM mechanism demo.
- Build the Docker image used by the public mock WebUI.

The existing `.gitlab-ci.yml` remains because the final course checklist explicitly requires a
`unit-test` job in that file. GitHub Actions is added because section 4.8 separately requires it
for every push and requires a container build for container distribution.

## Verification And Failure Handling

- A repository test parses the workflow and verifies triggers and required commands before the
  workflow is added.
- Local pytest, Ruff, the mechanism demo, and diff checks must pass before pushing.
- Authentication or remote errors stop the process without changing `main` or force-pushing.
- The PR description records the Superpowers workflow, subagent reviews, controller corrections,
  TDD evidence location, verification results, and remaining external deployment/reflection gates.

## Out Of Scope

- Automatically merging the Pull Request.
- Fabricating a public deployment URL or CI result.
- Writing the student-authored reflection.
- Modifying or discarding files in the main worktree.
