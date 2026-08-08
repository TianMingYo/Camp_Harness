# FeedbackLoop Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build a local-repository Coding Agent Harness that turns natural-language small-feature requests into approved, bounded edits and uses deterministic test/lint/type feedback to drive up to five correction iterations.

**Architecture:** A Python core owns the state machine, structured action protocol, workspace boundary, policy engine, command runner, validation detector, feedback classifier, context builder, persistence, and loop orchestration. FastAPI exposes asynchronous task and approval APIs with a small operator WebUI. The same core runs locally with an OpenAI-compatible client or offline mock LLM, while the public Docker demo uses only a disposable built-in repository and deterministic mock scenarios.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, httpx, keyring, SQLite, pytest, Docker, GitLab CI.

## Global Constraints

- No production implementation code is written until this SPEC, this PLAN, and the required cold-start validation have passed review.
- The delivered harness core must implement its own loop: context → LLM call → action parse → policy → tool execution → feedback → stop/continue.
- Do not use LangChain AgentExecutor, AutoGen, CrewAI, LlamaIndex Agent, or any provider/host agent runner.
- Every behavior-changing task follows RED → GREEN → REFACTOR; each plan task records the failing test command and the expected failure before implementation.
- LLM output proposes actions only. It never receives direct filesystem or shell privileges.
- The local mode only writes under a canonical Git repository root; dangerous commands, deletion, network, sensitive files, repository-outside paths, and Git push require HITL approval.
- Validation commands are auto-detected and user-overridable; the final command list is shown before plan approval.
- The default maximum is 5 iterations, task-level overrides require an upper bound, and two consecutive equivalent results produce `NO_PROGRESS`.
- Real providers use an OpenAI-compatible single-turn HTTP API. Unit and mechanism-demo tests use a deterministic mock LLM with no network.
- API keys are stored through the operating-system keyring and never written to source, Git, SQLite, logs, or terminal history.
- Long-running work is asynchronous. The p95 1-second short-request figure is a reference-environment baseline, not a cross-deployment hard gate.
- The public demo uses an embedded sample repository, a temporary workspace, and a mock LLM; it accepts no local paths or real keys.
- The final tree must include README, Dockerfile, `SPEC.md`, `PLAN.md`, `SPEC_PROCESS.md`, `AGENT_LOG.md`, human-authored `REFLECTION.md`, `.gitlab-ci.yml` with a `unit-test` job, and a reproducible public WebUI URL.
- Each task ends with a focused test run and a commit. `PLAN.md` is updated with the commit hash as tasks complete.

## File Map

Create the following focused units:

- `pyproject.toml`: package metadata, runtime dependencies, test command, and console entry point.
- `src/feedbackloop/models.py`: enums and Pydantic/dataclass models for tasks, actions, results, feedback, approvals, and validation commands.
- `src/feedbackloop/state.py`: deterministic task state machine and legal transitions.
- `src/feedbackloop/workspace.py`: canonical repository discovery, safe path resolution, and workspace fingerprints.
- `src/feedbackloop/policy.py`: command/path/sensitive-file risk decisions and approval requirements.
- `src/feedbackloop/validation.py`: command detection, user overrides, and bounded subprocess execution.
- `src/feedbackloop/feedback.py`: result classification, log redaction/truncation, and no-progress detection.
- `src/feedbackloop/llm.py`: provider protocol, OpenAI-compatible client, structured response parser, and deterministic mock client.
- `src/feedbackloop/context.py`: bounded context construction from task, plan, recent feedback, and relevant file summaries.
- `src/feedbackloop/store.py`: SQLite repositories for task, iteration, action, approval, feedback, provider metadata, and audit events.
- `src/feedbackloop/credentials.py`: keyring-backed set/get-status/update/clear service with a testable protocol.
- `src/feedbackloop/loop.py`: the project-owned feedback loop orchestrator.
- `src/feedbackloop/api.py`: FastAPI application, asynchronous task manager, task/approval endpoints, and demo-mode guard.
- `src/feedbackloop/web/index.html`: operator screens and accessible status structure.
- `src/feedbackloop/web/app.js`: API calls, polling/event handling, timeline rendering, and approval actions.
- `src/feedbackloop/web/styles.css`: compact operator-console layout and responsive states.
- `tests/unit/`: deterministic unit tests for every core mechanism.
- `tests/integration/`: temporary Git repository and API integration tests.
- `tests/demo/`: fixed mock-LLM mechanism demonstration assertions.
- `demo/scenario.py`: command-line reproducible demo runner used by CI and README.
- `Dockerfile`: public mock demo image with no credentials or host mounts.
- `.gitlab-ci.yml`: `unit-test` job and demo smoke test.
- `README.md`: install, local run, keyring setup, safe operation, Docker demo, limits, and deployment instructions.
- `REFLECTION.md`: created and written by the student, not generated by the agent; use the required questions as a writing checklist.

## Dependency Order

`Task 0` is a mandatory pre-implementation gate. `Tasks 1–6` provide independent core units in sequence. `Task 7` integrates them. `Task 8` exposes the API and WebUI. `Task 9` adds the demo, packaging, CI, and documentation. A task may run in its own worktree only after its predecessors' public interfaces are committed.

### Task 0: Cold-Start Specification Validation Gate

**Files:**
- Read: `SPEC.md`, `PLAN.md`
- Modify: `SPEC_PROCESS.md` only if the cold-start agent finds an ambiguity
- Modify: `AGENT_LOG.md` with the agent type, prompt, pause points, findings, and revisions

**Interfaces:**
- Consumes: only the approved `SPEC.md` and `PLAN.md`.
- Produces: a written cold-start report and an explicit go/no-go decision before any production code.

- [ ] **Step 1: Prepare an isolated clean checkout**

Use a fresh session with a different supported coding-agent type from the primary Codex session. Provide only the absolute paths to `SPEC.md` and `PLAN.md`, and the instruction: “Implement Tasks 1–2 only; when any requirement is ambiguous, pause and ask instead of guessing.”

- [ ] **Step 2: Run the cold-start agent**

Record where it pauses, which interfaces it interprets differently, and whether it can identify the required failing tests without oral context. Do not merge or copy its production code.

- [ ] **Step 3: Revise the spec or plan from evidence**

For each finding, record the before/after wording and the reason. If the second agent cannot be made available, stop and ask the user to choose a supported second agent; do not silently claim this gate passed.

- [ ] **Step 4: Verify the gate**

Expected: `SPEC_PROCESS.md` contains at least three iterations overall and the cold-start section contains the second agent type, prompt, pause points, findings, and final decision.

- [ ] **Step 5: Commit**

```bash
git add SPEC_PROCESS.md AGENT_LOG.md
git commit -m "docs: record cold-start specification validation"
```

### Task 1: Package Skeleton, Models, and State Machine

**Files:**
- Create: `pyproject.toml`, `src/feedbackloop/__init__.py`, `src/feedbackloop/models.py`, `src/feedbackloop/state.py`
- Test: `tests/unit/test_state.py`, `tests/unit/test_models.py`

**Interfaces:**
- Produces `TaskState`, `TaskEvent`, `Task`, `Action`, `ValidationCommand`, `Feedback`, `Approval`, `IterationRecord`.
- `Action.read(path)`, `Action.write(path, content)`, and `Action.delete(path)` are the only test and orchestration factories for filesystem actions.
- Produces `TaskStateMachine(current: TaskState)` with `transition(event: TaskEvent) -> TaskState` and `can_accept(event: TaskEvent) -> bool`.

- [ ] **Step 1: Write the failing model/state tests**

```python
def test_new_task_starts_in_draft():
    task = Task.create(repo_root="/repo", request="add a greeting command")
    assert task.state is TaskState.DRAFT

def test_approved_plan_enters_running():
    machine = TaskStateMachine(TaskState.AWAITING_PLAN_APPROVAL)
    assert machine.transition(TaskEvent.PLAN_APPROVED) is TaskState.RUNNING

def test_running_task_cannot_skip_to_success_without_validation():
    machine = TaskStateMachine(TaskState.RUNNING)
    assert machine.can_accept(TaskEvent.MARK_SUCCEEDED) is False
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run `python -m pytest tests/unit/test_models.py tests/unit/test_state.py -q`. Expected: collection fails because the package and symbols do not yet exist.

- [ ] **Step 3: Implement the smallest typed models and legal transition table**

Use immutable-enough Pydantic models for serialized records and an explicit transition dictionary. Reject unknown events and illegal state changes with a domain exception; do not add persistence or execution behavior here.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same command. Expected: all model and transition tests pass with no warnings.

- [ ] **Step 5: Refactor names and serialization only while green, then commit**

```bash
git add pyproject.toml src/feedbackloop tests/unit/test_models.py tests/unit/test_state.py
git commit -m "feat: add task domain models and state machine"
```

### Task 2: Workspace Boundary and Policy Engine

**Files:**
- Create: `src/feedbackloop/workspace.py`, `src/feedbackloop/policy.py`
- Test: `tests/unit/test_workspace.py`, `tests/unit/test_policy.py`

**Interfaces:**
- `Workspace(root: Path)` exposes `resolve_repo() -> Path`, `resolve_child(candidate: str) -> Path`, and `fingerprint() -> str`.
- `PolicyEngine.check(action: Action, workspace: Workspace) -> PolicyDecision` returns `ALLOW`, `REQUIRE_APPROVAL`, or `DENY` with a reason.

- [ ] **Step 1: Write failing boundary and risk tests**

```python
def test_resolve_child_rejects_parent_escape(tmp_path):
    workspace = Workspace(tmp_path)
    with pytest.raises(PathBoundaryError):
        workspace.resolve_child("../outside.txt")

def test_policy_requires_approval_for_delete(tmp_path):
    decision = PolicyEngine().check(Action.delete("inside.txt"), Workspace(tmp_path))
    assert decision.kind is DecisionKind.REQUIRE_APPROVAL

def test_policy_denies_sensitive_file_read(tmp_path):
    decision = PolicyEngine().check(Action.read(".env"), Workspace(tmp_path))
    assert decision.kind is DecisionKind.DENY
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/unit/test_workspace.py tests/unit/test_policy.py -q`. Expected: missing-module or missing-symbol failures.

- [ ] **Step 3: Implement canonical path checks and explicit risk rules**

Resolve symlinks before containment checks, compare normalized paths against the repository root, and classify delete, network, Git push, sensitive-file access, shell chaining, and undeclared commands. Keep the policy pure and deterministic.

- [ ] **Step 4: Run tests and verify GREEN**

Run the focused command. Expected: safe in-repo reads/writes are allowed, dangerous actions require approval, and sensitive or escaped paths are denied.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/workspace.py src/feedbackloop/policy.py tests/unit/test_workspace.py tests/unit/test_policy.py
git commit -m "feat: enforce workspace boundaries and action policy"
```

### Task 3: Validation Detection and Bounded Command Runner

**Files:**
- Create: `src/feedbackloop/validation.py`
- Test: `tests/unit/test_validation.py`, `tests/integration/test_command_runner.py`

**Interfaces:**
- `ValidationDetector.detect(repo_root: Path) -> list[ValidationCommand]`.
- `ValidationDetector.apply_overrides(detected, overrides) -> list[ValidationCommand]`.
- `CommandRunner.run(command: ValidationCommand, cwd: Path) -> CommandResult`.

- [ ] **Step 1: Write failing detection and execution tests**

```python
def test_detects_pytest_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    commands = ValidationDetector.detect(tmp_path)
    assert any(command.kind == "test" for command in commands)

def test_runner_returns_timeout_without_hanging(tmp_path):
    command = ValidationCommand(kind="test", executable=sys.executable,
                                args=("-c", "import time; time.sleep(1)"), timeout_seconds=0.01)
    result = CommandRunner().run(command, tmp_path)
    assert result.timed_out is True
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/unit/test_validation.py tests/integration/test_command_runner.py -q`. Expected: missing detector/runner behavior.

- [ ] **Step 3: Implement conservative detectors and subprocess execution**

Support Python, Node, and Rust project markers with explicit command arrays. Apply user overrides after detection. Capture exit code, stdout, stderr, duration, and timeout; enforce a maximum output size and never invoke a shell by default.

- [ ] **Step 4: Run tests and verify GREEN**

Run the focused command and verify detection, override precedence, non-zero exits, missing executables, output truncation, and timeout behavior.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/validation.py tests/unit/test_validation.py tests/integration/test_command_runner.py
git commit -m "feat: detect validation commands and run them safely"
```

### Task 4: Feedback Classification and Progress Detection

**Files:**
- Create: `src/feedbackloop/feedback.py`
- Test: `tests/unit/test_feedback.py`

**Interfaces:**
- `FeedbackClassifier.classify(result: CommandResult, before: str, after: str) -> Feedback`.
- `ProgressTracker.changed(before: str, after: str, previous_feedback: Feedback | None) -> bool`.
- `redact_and_truncate(text: str, max_chars: int) -> str`.

- [ ] **Step 1: Write failing feedback tests**

```python
def test_nonzero_test_result_is_test_failure():
    result = CommandResult(kind="test", exit_code=1, stdout="FAILED test_greeting", stderr="")
    feedback = FeedbackClassifier().classify(result, "before", "after")
    assert feedback.kind is FeedbackKind.TEST_FAILURE

def test_equal_workspace_and_feedback_is_no_progress():
    tracker = ProgressTracker()
    assert tracker.changed("same", "same", Feedback(kind=FeedbackKind.TEST_FAILURE)) is False
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/unit/test_feedback.py -q`. Expected: missing classifier, progress, and redaction behavior.

- [ ] **Step 3: Implement deterministic category rules and fingerprints**

Prioritize timeout, policy, command-start errors, test/build/lint categories, then pass. Hash sorted relative file paths and contents for workspace fingerprints. Treat identical fingerprint plus equivalent feedback as no progress. Redact common API-key and bearer-token patterns before persistence.

- [ ] **Step 4: Run tests and verify GREEN**

Run the focused command with fixtures for every enum, pass, timeout, output truncation, redaction, changed files, and two consecutive no-progress rounds.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/feedback.py tests/unit/test_feedback.py
git commit -m "feat: classify validation feedback and detect no progress"
```

### Task 5: Structured LLM Adapter and Context Builder

**Files:**
- Create: `src/feedbackloop/llm.py`, `src/feedbackloop/context.py`
- Test: `tests/unit/test_llm.py`, `tests/unit/test_context.py`

**Interfaces:**
- `LLMClient.complete(context: AgentContext) -> LLMResponse`.
- `CredentialProvider.get(provider: str) -> str | None` is a small protocol defined with the adapter and implemented by Task 6's keyring service.
- `OpenAICompatibleClient(base_url: str, model: str, credential_provider: CredentialProvider)`.
- `MockLLM(responses: list[LLMResponse])`.
- `parse_action_response(payload: str) -> list[Action]`.
- `ContextBuilder.build(task: Task, plan: Plan, recent: list[IterationRecord], files: list[FileSummary]) -> AgentContext`.

- [ ] **Step 1: Write failing parser, mock, and context tests**

```python
def test_parser_rejects_unknown_action_type():
    with pytest.raises(InvalidLLMResponse):
        parse_action_response('{"actions":[{"type":"invent"}]}')

def test_context_is_bounded_to_recent_feedback():
    context = ContextBuilder(max_recent_iterations=2).build(task, plan, records, files)
    assert len(context.recent_iterations) == 2
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/unit/test_llm.py tests/unit/test_context.py -q`. Expected: missing protocol/parser/context behavior.

- [ ] **Step 3: Implement provider-neutral structured calls and bounded context**

Send one request to an OpenAI-compatible `/chat/completions`-style endpoint through `httpx`, pass credentials only at request time, validate JSON actions with Pydantic, and return typed errors for HTTP, timeout, malformed, or refusal responses. Keep `MockLLM` deterministic and context construction bounded to relevant summaries.

- [ ] **Step 4: Run tests and verify GREEN**

Use `httpx.MockTransport` for provider tests and no network. Verify malformed output, provider errors, mock sequencing, context truncation, and sensitive-content exclusion.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/llm.py src/feedbackloop/context.py tests/unit/test_llm.py tests/unit/test_context.py
git commit -m "feat: add structured provider adapter and bounded context"
```

### Task 6: SQLite Audit Store and Keyring Credentials

**Files:**
- Create: `src/feedbackloop/store.py`, `src/feedbackloop/credentials.py`
- Test: `tests/unit/test_store.py`, `tests/unit/test_credentials.py`

**Interfaces:**
- `Store.create_task`, `save_plan`, `save_iteration`, `save_action`, `save_feedback`, `save_approval`, `append_audit_event`, and corresponding `get_*` methods.
- `CredentialService.set(provider, key)`, `status(provider)`, `clear(provider)`, and `build_provider(provider) -> CredentialProvider`.
- `KeyringProtocol.get/set/delete` is injected so tests never use a real user keyring.

- [ ] **Step 1: Write failing persistence and credential tests**

```python
def test_store_round_trips_iteration_and_feedback(tmp_path):
    store = Store(tmp_path / "tasks.sqlite3")
    store.save_iteration(iteration)
    store.save_feedback(feedback)
    assert store.get_feedback(iteration.id).kind is FeedbackKind.TEST_FAILURE

def test_credential_status_never_returns_secret():
    keyring = MemoryKeyring()
    service = CredentialService(keyring)
    service.set("demo", "secret-value")
    assert service.status("demo").configured is True
    assert "secret-value" not in repr(service.status("demo"))
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/unit/test_store.py tests/unit/test_credentials.py -q`. Expected: missing schema/repository/keyring behavior.

- [ ] **Step 3: Implement transactional SQLite repositories and keyring adapter**

Create the schema with foreign keys and unique task/iteration constraints. Store only redacted summaries and provider metadata. Implement set, status, update, and clear through the injected keyring protocol; never log key values.

- [ ] **Step 4: Run tests and verify GREEN**

Verify round trips, rollback on invalid references, redacted audit payloads, update/clear behavior, and provider metadata persistence with an in-memory keyring.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/store.py src/feedbackloop/credentials.py tests/unit/test_store.py tests/unit/test_credentials.py
git commit -m "feat: persist audit records and protect provider credentials"
```

### Task 7: Feedback Loop Orchestrator

**Files:**
- Create: `src/feedbackloop/loop.py`
- Test: `tests/unit/test_loop.py`, `tests/demo/test_mechanisms.py`

**Interfaces:**
- `FeedbackLoop(task_store, llm, policy, executor, classifier, context_builder, max_iterations).run(task_id) -> TaskResult`.
- `FeedbackLoop.approve_plan(task_id) -> TaskState`.
- `FeedbackLoop.resolve_approval(approval_id, decision) -> TaskState`.

- [ ] **Step 1: Write the failing end-to-end mock loop test**

```python
def test_loop_uses_failure_feedback_to_reach_pass(fake_components):
    fake_components.llm = MockLLM([
        Action.write("src/greeting.py", "return broken"),
        Action.write("src/greeting.py", "return fixed"),
    ])
    result = FeedbackLoop(**fake_components).run("task-1")
    assert result.state is TaskState.SUCCEEDED
    assert [item.feedback.kind for item in result.iterations] == [FeedbackKind.TEST_FAILURE, FeedbackKind.PASS]
```

- [ ] **Step 2: Run the test and verify RED**

Run `python -m pytest tests/unit/test_loop.py::test_loop_uses_failure_feedback_to_reach_pass -q`. Expected: the orchestrator is absent and the test fails.

- [ ] **Step 3: Implement the minimum orchestration loop**

Load the approved plan, build bounded context, call the LLM once per iteration, parse actions, evaluate policy, execute allowed actions, run validation, classify feedback, persist all records, and transition state. Enforce pass, policy pause, no-progress pause, timeout, and max-iteration stop without model judgment.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same test and then `python -m pytest tests/unit/test_loop.py tests/demo/test_mechanisms.py -q`. Expected: the mock scenario passes and the demo also proves a dangerous action is blocked.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/loop.py tests/unit/test_loop.py tests/demo/test_mechanisms.py
git commit -m "feat: orchestrate deterministic feedback correction loop"
```

### Task 8: FastAPI API and Operator WebUI

**Files:**
- Create: `src/feedbackloop/api.py`, `src/feedbackloop/web/index.html`, `src/feedbackloop/web/app.js`, `src/feedbackloop/web/styles.css`
- Test: `tests/integration/test_api.py`

**Interfaces:**
- `POST /tasks` creates and scans a task.
- `POST /tasks/{task_id}/plan/approve` approves the plan and starts asynchronous execution.
- `GET /tasks/{task_id}` returns current state, plan, iterations, feedback, and pending approvals.
- `POST /approvals/{approval_id}` records an allow/deny decision.
- `POST /providers/{provider}/credentials` sets or updates a key without echoing it.
- `DELETE /providers/{provider}/credentials` clears a key.
- `GET /demo/scenario` returns the fixed public mock scenario.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_create_task_returns_detected_validation_commands(client, repo):
    response = client.post("/tasks", json={"repo_path": str(repo), "request": "add greeting"})
    assert response.status_code == 201
    assert response.json()["validation_commands"]

def test_secret_is_not_returned_by_credential_endpoint(client):
    response = client.post("/providers/demo/credentials", json={"key": "secret"})
    assert response.status_code == 204
    assert "secret" not in response.text
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/integration/test_api.py -q`. Expected: the FastAPI app and routes are missing.

- [ ] **Step 3: Implement asynchronous task endpoints and operator screens**

Use an in-process task manager for the first release, return immediately for long-running work, and expose polling or server-sent progress events. Render plan approval, iteration timeline, structured feedback, and HITL decisions. Escape all log text before rendering and keep credential responses status-only.

- [ ] **Step 4: Run tests and verify GREEN**

Run the focused API tests, then `python -m pytest tests/unit tests/integration -q`. Verify task creation, plan approval, progress retrieval, approval decisions, credential redaction, and demo isolation.

- [ ] **Step 5: Commit**

```bash
git add src/feedbackloop/api.py src/feedbackloop/web tests/integration/test_api.py
git commit -m "feat: expose asynchronous task API and operator WebUI"
```

### Task 9: Reproducible Demo, Packaging, CI, and README

**Files:**
- Create: `demo/scenario.py`, `Dockerfile`, `.gitlab-ci.yml`, `README.md`, `.gitignore`, `REFLECTION.md`
- Modify: `AGENT_LOG.md`
- Test: `tests/demo/test_mechanisms.py`, CI pipeline

**Interfaces:**
- `python -m demo.scenario` runs the offline failure-feedback, correction, and policy-block demonstrations.
- `docker build -t feedbackloop-demo .` builds the public demo image.
- `docker run --rm -p 8000:8000 feedbackloop-demo` starts the mock WebUI.
- `.gitlab-ci.yml` contains a job exactly named `unit-test` and runs the one-command test suite.

- [ ] **Step 1: Write failing demo and packaging smoke tests**

```python
def test_demo_contains_feedback_correction_and_policy_block():
    result = run_demo()
    assert result.corrected_after_feedback is True
    assert result.policy_blocked is True
    assert result.used_network is False
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -m pytest tests/demo/test_mechanisms.py -q`. Expected: the demo entry point and container metadata are missing.

- [ ] **Step 3: Implement the offline demo and distribution files**

Use only the mock LLM and a temporary built-in repository. Document local installation, keyring setup, provider configuration, validation overrides, safety limits, Docker demo, deployment, and platform prerequisites. Add `.gitignore` entries for `.env`, SQLite data, logs, caches, virtual environments, and build output. Create `REFLECTION.md` as a human-owned file containing the course questions; the student writes its 1500–2500 Chinese characters.

- [ ] **Step 4: Run the complete verification**

Run `python -m pytest -q`, `python -m demo.scenario`, `docker build -t feedbackloop-demo .`, and a local container smoke request to `/demo/scenario`. Confirm the final CI pipeline's `unit-test` job is green and record the public WebUI URL.

- [ ] **Step 5: Commit**

```bash
git add demo Dockerfile .gitlab-ci.yml README.md .gitignore REFLECTION.md AGENT_LOG.md tests/demo
git commit -m "feat: package and demonstrate feedback-loop harness"
```

## Plan Self-Review

- **Spec coverage:** Tasks 1–2 cover models, state, workspace, and governance; Tasks 3–4 cover validation, objective feedback, and progress; Tasks 5–7 cover provider abstraction, context, persistence, credentials, and the project-owned loop; Task 8 covers the local WebUI; Task 9 covers demo, distribution, CI, README, and the human reflection. Task 0 covers the mandatory unfamiliar-agent cold start.
- **Instruction completeness scan:** No implementation step contains an unresolved or vague instruction; every task names files, interfaces, tests, commands, and expected results.
- **Type consistency:** `Task`, `Plan`, `Action`, `ValidationCommand`, `CommandResult`, `Feedback`, `IterationRecord`, and `TaskState` are introduced in Task 1 and used consistently by later tasks. The loop consumes the same typed results emitted by policy, executor, classifier, and store.
- **Known external gate:** A second supported agent type is required for Task 0 by the course document. Its availability and the final Git hosting/CI target must be confirmed before implementation; any deviation is recorded in `SPEC_PROCESS.md` and `AGENT_LOG.md`.
