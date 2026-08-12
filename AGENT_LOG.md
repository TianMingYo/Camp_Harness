# Agent Log

## 2026-08-08 - Toolchain and brainstorming bootstrap

- **Task:** pre-implementation project setup
- **Skills:** `using-superpowers`, `brainstorming`
- **Context:** Read `项目要求/AI4SE_Final_Project_通用要求.md` and `项目要求/AI4SE_Final_Project_A_Coding_Agent_Harness.md` as UTF-8. The workspace currently contains requirements documents only; `.git` is present but not a valid repository.
- **Toolchain:** Superpowers `6.2.0` is installed and enabled for Codex. `multi_agent` is enabled. The plugin source is the official `obra/superpowers` repository at commit `44c9b2d6e889982ac18c27d05a19fefe335194e1`.
- **Human decisions:** feedback loop as the main contribution; natural-language small feature implementation; local Git repository path; automatic validation detection with user override; plan approval followed by autonomous safe in-repo execution; OpenAI-compatible API; local full WebUI plus public mock demo; default maximum 5 iterations.
- **Subagents:** none yet; implementation is blocked by the brainstorming hard gate until SPEC and PLAN are approved and cold-start validation is complete.
- **Manual intervention:** user approved four design sections. No production code has been written.
- **Repository intervention:** the provided `.git` directory was empty/invalid and read-only in the sandbox; after explicit approval it was initialized locally, and the design documents were committed as `a26df5c`.
- **Specification revision:** after reviewing `SPEC.md`, the human owner rejected a fixed 500ms UI response requirement as deployment-dependent. The performance section now uses a reference-environment p95 baseline, asynchronous long-running work, and measured deployment results. No functional acceptance criteria were weakened.
- **Plan checkpoint:** `writing-plans` produced `docs/superpowers/plans/2026-08-08-feedback-loop-harness.md` and the course-required root mirror `PLAN.md`. The self-review found and fixed three interface issues before saving the plan: filesystem action factories, the credential-provider protocol, and the mock-loop constructor. Both plan files have the same SHA-256 hash.
- **Lesson:** deterministic feedback classification and explicit execution boundaries must remain in project code, not prompts; model output is only an action proposal.

## 2026-08-08 - SDD cold-start gate

- **Task:** independent cold-start validation of PLAN Tasks 1-2 before implementation.
- **Context restriction:** each attempt received only `SPEC.md` and `PLAN.md` in a fresh temporary directory; no prior conversation, source tree, or repository context was supplied.
- **Gemini CLI 0.39.0:** default `gemini-3.1-pro-preview` and explicit `gemini-2.5-flash` each exhausted ten retries with `503 model_not_found` and created no files.
- **Claude Code 2.1.118:** initially could not discover Git Bash. After configuring the existing portable `bash.exe` through `CLAUDE_CODE_GIT_BASH_PATH`, it started but exited after about three minutes with `API Error: Unable to connect to API (ConnectionRefused)` before attempting either task.
- **Result:** Task 0 is blocked by external supported-agent availability. No production code was written. Detailed evidence is in the SDD workspace cold-start reports.
- **Deviation:** SDD implementation dispatch is paused rather than silently replacing the required fresh-agent gate. Human approval is required to provide an available second-agent model/provider or authorize proceeding with this documented deviation.

## 2026-08-10 - Cold-start gate rerun with Claude Code / GLM 5.2

- **Agent type:** Claude Code 2.1.118, configured by the human with the GLM 5.2 model.
- **Context restriction:** fresh session received only `SPEC.md` and `PLAN.md`; no prior conversation, memory, repository source, or generated implementation was supplied.
- **Attempt:** independently drafted Task 1-2 tests and implementation, but did not commit or merge any files.
- **TDD evidence:** the agent documented the expected RED failures and static GREEN reasoning, but the unattended CLI could not obtain approval to run Python/pytest. Runtime GREEN is therefore unverified.
- **Findings:** the state transition gate, real-Git-root requirement, sensitive-delete precedence, and non-filesystem action model were underspecified.
- **Revision:** SPEC and PLAN now explicitly define `VALIDATION_PASSED`, require `.git` markers for canonical workspaces, add command/network/Git-push actions, and make sensitive-file denial take precedence. The cold-start implementation remains isolated and is not part of the feature branch.
- **Decision:** cold-start specification review is GO after the documented revisions. The inability to run Python in the unattended secondary CLI is a recorded execution-environment deviation; every primary implementation task must still capture real RED and GREEN test runs before its commit.

## 2026-08-10 - Task 3 interface clarification

- **Finding:** the plan referenced `CommandResult` in validation, feedback, and loop interfaces but
  Task 1 had not assigned its ownership or fields.
- **Revision:** Task 3 now explicitly extends `models.py` with immutable `CommandResult(kind,
  exit_code, stdout, stderr, timed_out, duration_seconds, error)`; runner output is bounded before
  classification or persistence.
- **Execution deviation:** the collaboration dispatch channel and two fresh Claude Code/GLM 5.2
  implementation prompts were unavailable/rejected by the gateway. The primary controller then
  executed Task 3 TDD directly: RED was captured before implementation, GREEN and full regression
  were captured after implementation, and this takeover is recorded rather than attributed to a
  subagent.
- **Task 4 continuation:** the same collaboration dispatch limitation remained, so the controller
  performed Task 4 with two explicit RED/GREEN cycles, including a review-discovered policy
  priority test, before committing.
- **Task 5 continuation:** the controller retained direct TDD execution because the agent gateway
  remained unreliable. Provider tests use `httpx.MockTransport`; no real key or network request
  was used.
- **Task 6 continuation:** direct TDD used an isolated SQLite database and injected memory keyring;
  the system keyring adapter was not invoked during tests.
- **Task 7 continuation:** the controller implemented the core loop directly after the same agent
  dispatch limitation. Tests use a temporary repository, SQLite store, deterministic MockLLM, and
  fake executor; no real provider or shell command is used.
- **Task 8 continuation:** FastAPI/Uvicorn were installed from official PyPI after the configured
  mirror returned no packages. API tests use TestClient and memory credentials; no server or real
  key is started during unit/integration verification.
- **Task 9 verification:** editable installation and both demo entry points passed. Docker CLI is
  not installed, so image build/container smoke remain external gates. GitLab CI and a public WebUI
  URL also require the student's remote repository/deployment credentials and are not fabricated.
- **Academic boundary:** `REFLECTION.md` contains only the required question template because the
  course explicitly requires the 1500-2500-character report to be written by the student.
- **Final contract review fix:** a real-loop API integration test found that task creation left the
  state at `DRAFT`, making plan approval illegal. The API now transitions through `PLAN_READY` to
  `AWAITING_PLAN_APPROVAL`; the focused test was RED before the fix and GREEN after it. SQLite
  connections were also changed to operation-scoped close semantics after the demo exposed a
  Windows file lock.
- **Final review:** the Claude Code / GLM 5.2 whole-branch review was rejected by the provider's
  `sensitive_words_detected` filter, so the external result is unavailable. Controller review
  found that public demo mode still accepted credential writes; a RED integration test reproduced
  it, and public-demo credential set/clear now return 403 while local mode remains enabled.

## 2026-08-10 - Local runtime and HITL contract completion

- **Root cause review:** the default local FastAPI app had no production composition root or local
  executor, so plan approval returned 503 even though the README described real-provider local
  execution. Validation override logic also existed only below the API boundary, and pending
  approvals were not exposed to the WebUI.
- **TDD evidence:** focused RED runs reproduced the missing `LocalExecutor`, local approval 503,
  sensitive `.env` summary read, ignored validation overrides, absent provider/validation UI,
  approved actions not executing, resumed iteration numbering collision, approval endpoints not
  restarting work, missing pending-approval status, and uncaught provider failures. Each focused
  test passed after its minimal implementation before the next behavior was started.
- **Implementation:** commit `00296ae` adds a canonical-root `LocalExecutor`, per-task provider/base
  URL/model configuration, structured validation overrides, local loop construction, provider
  failure feedback, approval listing and UI decisions, approved action execution, and asynchronous
  resume at the next persisted iteration number.
- **Regression check:** the first complete run caught a misplaced function boundary that made
  `build_local_loop` return `None`; the focused local-app test failed, the function boundary was
  corrected, and the focused tests plus complete suite were rerun. Final pre-documentation result:
  `99 passed, 1 skipped, 1 warning`.
- **Safety evidence:** all provider tests monkeypatch or mock the external call, credential tests use
  an in-memory keyring, sensitive summaries are excluded before file reads, and the real-secret scan
  found no matching key patterns. No real provider key or network call was used during tests.
- **Known boundary:** network, Git push, and undeclared command proposals remain policy-gated and are
  not executed by the local executor. Docker, remote GitLab CI, public deployment, and the
  student-written reflection remain external completion gates.

## 2026-08-11 - Independent review hardening

- **Review source:** an independent read-only Superpowers code review of `4c5f69f..58399a6`
  reported critical gaps around eager repository context reads, opaque approval scope, empty
  validation success, public-demo data isolation, unsupported approved actions, uncaught executor
  failures, audit status, `auto_execute`, and fabricated Git markers.
- **Verification:** each accepted issue was checked against the current code and converted into a
  focused RED test before production edits. The plan now requires explicit repository-relative
  file paths, local provider configuration, and at least one validation command; `Workspace` asks
  Git for the canonical top-level; summaries read only explicit non-secret files; public demo uses
  isolated storage and exposes no task/approval execution routes; unsupported local actions are
  denied; executor/provider failures become persisted `COMMAND_ERROR` and `FAILED`; action status,
  approval decisions, and redacted audit events are queryable; `auto_execute=False` is rejected.
- **TDD process deviation:** one initial patch accidentally included production edits with the new
  tests. The edits were immediately reverted before the focused test run; the same behavior was
  then reintroduced only after observing the expected RED failures. No implementation commit was
  made from the premature patch.
- **Verification result:** focused hardening tests and the complete suite pass with `112 passed,
  1 skipped, 1 warning`; both offline demo entry points, compileall, diff check, and secret scan
  also pass. The symlink test skip remains Windows privilege-related. Docker, remote CI, public URL,
  and student reflection remain external gates.

## 2026-08-11 - Structured planning and audit review closure

- **Review verification:** the remaining independent findings were checked against the current
  branch. The accepted gaps were missing Plan approval timestamps and state audits, false
  `progressed` values, contradictory no-progress feedback, lost partial-action outcomes, missing
  total context budgets, late validation executable failures, and request-echo plans that did not
  satisfy SPEC 4.3.
- **TDD evidence:** focused RED runs reproduced each behavior before its production fix. The loop
  now persists Plan approval time, state transitions, per-action completion/failure, truthful
  fingerprints, explicit `NO_PROGRESS`, and stop-reason audits. Plan parsing, OpenAI-compatible
  plan generation, asynchronous API state, file-scope enforcement, validation-command integrity,
  iteration bounds, raw-response redaction, and WebUI approval timing each have focused tests.
- **Temporary TDD deviation and correction:** the first asynchronous planning GREEN patch included
  repository-summary and three plan-boundary checks before those branches had focused RED tests.
  Those unproven lines were removed immediately. Four focused tests then failed for the expected
  missing behaviors, and only then were the same checks reintroduced and verified GREEN. No commit
  contains the premature implementation.
- **Frontend test environment:** the WebUI state module is exercised through Node.js when Node is
  available. The Python-only GitLab image may report this one supplemental test as skipped; API
  state and approval gating remain covered independently by Python integration tests.
- **Provider boundary:** all automated plan-generation tests use injected planners or
  `httpx.MockTransport`; no real key or network request is used. Claude Code configured with GLM
  5.2 remains the cold-start/review CLI only and does not receive write authority over this branch.

### Focused RED/GREEN evidence

All Python commands below used `C:\Users\13900\anaconda3\python.exe -m pytest ... -q` from the
feature worktree. Each command was rerun unchanged after the minimal implementation patch.

| Behavior | Focused pytest nodeid(s) | Observed RED | GREEN |
| --- | --- | --- | --- |
| Plan approval time and state audit | `tests/unit/test_loop.py::test_plan_approval_persists_timestamp_and_state_audit` | `Plan` had no `approved_at` | `1 passed` |
| Truthful progress and no-progress feedback | `tests/unit/test_loop.py::test_loop_uses_failure_feedback_to_reach_pass tests/unit/test_loop.py::test_two_equivalent_rounds_pause_for_no_progress` | progress was always false; final kind was `TEST_FAILURE` | `2 passed` |
| API audit exposure | `tests/integration/test_api.py::test_task_create_approve_and_get_status` | `audit_events` key missing | `1 passed` |
| Partial action persistence | `tests/unit/test_loop.py::test_partial_action_failure_persists_each_action_outcome` | stored action list was empty | `1 passed` |
| Complete structured Plan parser | `tests/unit/test_llm.py::test_plan_parser_requires_complete_structured_plan` | `parse_plan_response` missing | `1 passed` |
| OpenAI-compatible plan generation | `tests/unit/test_llm.py::test_openai_compatible_client_generates_structured_plan` | `generate_plan` missing | `1 passed` |
| Async planning success/failure | `tests/integration/test_api.py::test_task_create_approve_and_get_status tests/integration/test_api.py::test_plan_generation_failure_is_persisted_without_a_plan` | `create_app` rejected `planner` injection | `2 passed` |
| Repository summary and Plan limits | `tests/integration/test_api.py::test_planner_receives_bounded_repository_summary tests/integration/test_api.py::test_generated_plan_cannot_expand_authorized_file_scope tests/integration/test_api.py::test_generated_plan_cannot_change_harness_limits` | empty summary and unauthorized plans entered approval | `4 passed` |
| Raw invalid-plan redaction | `tests/unit/test_llm.py::test_invalid_plan_response_retains_raw_content_for_boundary_redaction tests/unit/test_feedback.py::test_redaction_handles_json_credential_fields tests/integration/test_api.py::test_invalid_plan_audit_keeps_only_redacted_raw_summary` | raw content unavailable; JSON secret leaked; audit lost diagnostic | focused tests passed |
| WebUI async approval state | `tests/unit/test_web_state.py::test_async_planning_controls_approval_and_polling` | Node `ERR_MODULE_NOT_FOUND` for state module | `1 passed` |
| Explicit stop audits | `tests/unit/test_loop.py::test_two_equivalent_rounds_pause_for_no_progress tests/unit/test_loop.py::test_iteration_limit_pauses_with_explicit_stop_audit` | last event was only a state transition | `2 passed` |
| Post-action exception consistency | `tests/unit/test_loop.py::test_partial_action_failure_persists_each_action_outcome tests/unit/test_loop.py::test_validation_exception_updates_existing_iteration_and_fails_task` | false progress and SQLite iteration uniqueness error | `2 passed` |
| Objective success gate audit | `tests/unit/test_loop.py::test_loop_uses_failure_feedback_to_reach_pass` | audit jumped directly from running to succeeded | `1 passed` |
| Approved action execution failure | `tests/unit/test_loop.py::test_approved_action_failure_marks_action_and_audits_real_transitions` | failed action remained proposed | `1 passed` |
| Shared sensitive-path policy | `tests/integration/test_api.py::test_task_creation_normalizes_plan_paths_and_rejects_unsafe_scope tests/unit/test_context.py::test_context_excludes_sensitive_files_and_bounds_summary` | `.npmrc` and private key paths were accepted | `2 passed` |
| Restart-safe no-progress streak | `tests/unit/test_loop.py::test_no_progress_streak_is_reconstructed_from_persisted_iterations` | task exhausted mock response and failed instead of pausing | `1 passed` |
| Complete mixed action batch | `tests/unit/test_loop.py::test_mixed_safe_and_dangerous_batch_persists_every_proposed_action` | safe write disappeared | `1 passed` |
| Planner configuration error | `tests/integration/test_api.py::test_injected_loop_requires_explicit_planner_or_provider` | assertion escaped as server error | `1 passed` |
| Same-kind validation override | `tests/unit/test_validation.py::test_overrides_replace_only_commands_of_the_same_kind` | unrelated lint command was discarded | `1 passed` |
| Approval batch action order | `tests/unit/test_loop.py::test_approval_batch_preserves_model_action_order` | safe suffix executed before the earlier delete approval | `1 passed` |
| Unavailable post-action fingerprint | `tests/unit/test_loop.py::test_post_action_fingerprint_failure_records_known_progress` | completed write was recorded as no progress | `1 passed` |
| Unexpected approved-action exception | `tests/unit/test_loop.py::test_unexpected_approved_action_exception_is_controlled` | `AssertionError` escaped and left action proposed | `1 passed` |

### Review evidence

- Claude Code used the configured GLM 5.2 model as requested. The first read-only review timed out;
  the escalated retry ended in `ConnectionRefused`; a final approved retry produced no output and
  was terminated. No Claude process modified the worktree.
- An independent read-only reviewer then reproduced the post-action iteration collision and
  identified seven Important consistency issues. Every actionable code issue was converted to a
  focused RED test and fixed. The reviewer also requested exact TDD evidence; this table is the
  resulting audit record.
- **Second review:** the same reviewer confirmed the original Critical and Important findings were
  closed, then found three follow-on ordering/error-boundary issues. Approval-containing batches
  now pause in full and execute in original order after approval; an unavailable post-action
  fingerprint is stored as `unavailable` with known mutation evidence; approved actions catch all
  ordinary exceptions. Each follow-on issue has the RED/GREEN evidence above.
- **Post-review verification:** `ruff check src tests demo` passed; the complete suite reported
  `140 passed, 1 skipped, 1 warning`; compileall, both offline demo entry points, and
  `git diff --check` passed. The skip is the Windows symbolic-link privilege case and the warning
  is Starlette TestClient's httpx deprecation notice.

## Workflow commitment

The remaining Superpowers workflow is `writing-plans` → `using-git-worktrees` →
`subagent-driven-development` / `executing-plans` →
`test-driven-development` → `requesting-code-review` →
`finishing-a-development-branch`. Any deviation will be logged with its reason,
impact, human intervention and verification evidence.

## 2026-08-11 - GitHub Actions delivery contract

- **RED command:** `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_github_delivery.py -q`
- **RED result:** `FAILED tests/demo/test_github_delivery.py::test_github_workflow_runs_tests_demo_and_container_build`; `FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\13900\\Desktop\\作业\\智软训练营\\.worktrees\\feedback-loop-harness\\.github\\workflows\\ci.yml'`; `1 failed in 0.17s`.
- **Focused GREEN command:** `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_github_delivery.py -q`
- **Focused GREEN result:** `1 passed in 0.06s`.
- **Full regression command:** `C:\Users\13900\anaconda3\python.exe -m pytest -q`
- **Full regression result:** `141 passed, 1 skipped, 1 warning in 30.08s`; the skip is the documented Windows symbolic-link privilege case and the warning is Starlette TestClient's httpx deprecation notice.
- **Ruff command/result:** `ruff check src tests demo` -> `All checks passed!`
- **Demo command/result:** `C:\Users\13900\anaconda3\python.exe -m demo.scenario` -> `"corrected_after_feedback": true`, `"policy_blocked": true`, `"used_network": false`, `"final_state": "succeeded"`.
- **Diff command/result:** `git diff --check` exited `0`; Git emitted only the working-copy LF-to-CRLF notice for `pyproject.toml`.

## 2026-08-11 - GitHub Actions contract review fix

- **Review finding:** the original test concatenated all `run` values and checked substrings, so one echo-only step containing those strings could pass without executing checkout, Python setup, tests, the demo, or the image build.
- **Controlled mutation:** after strengthening the test, `.github/workflows/ci.yml` was temporarily changed to one folded `run` step: `echo python -m pip install ".[test]" python -m pytest -q python -m demo.scenario docker build -t feedbackloop-demo .`. The workflow name, triggers, job name, and runner remained valid, demonstrating the precise old-test false positive.
- **Mutation RED command:** `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_github_delivery.py -q`
- **Mutation RED result:** the exact ordered-step assertion failed at index `0`: the echo-only `run` mapping did not equal `{"uses": "actions/checkout@v4"}`; pytest also reported `Right contains 5 more items`; `1 failed in 0.14s`.
- **Restored GREEN command:** `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_github_delivery.py -q`
- **Restored GREEN result:** `1 passed in 0.05s`.
- **Strengthened contract:** the test now requires workflow name `CI`, exactly the `push` and `pull_request` triggers, exactly one `quality` job on `ubuntu-latest`, and the six exact ordered step mappings from checkout through Docker build.

## 2026-08-11 - GitHub Pull Request delivery

- **Approved target:** `https://github.com/TianMingYo/Camp_Harness.git`; feature branch `feature/feedback-loop-harness`; base branch `main`; no merge or force push.
- **Unexpected external state:** `git ls-remote` succeeded but returned no refs because the target repository was empty. The implementation plan assumed an existing `main` branch.
- **Plan deviation:** after verifying `main` (`951d4bb`) was the exact merge base and ancestor of the feature head, the controller published `main:main` with a normal non-force push. This created only the required PR baseline and did not switch, edit, stage, or commit the dirty main worktree.
- **Default-branch correction:** GitHub initially selected the first-pushed feature branch as the repository default. After `main` existed, the controller changed the remote default branch to `main` through the GitHub REST API so the repository and PR use the intended baseline.
- **PR-tool deviation:** GitHub CLI was unavailable. Instead of stopping at the documented compare-URL fallback, the controller used the existing Git credential through the GitHub REST API to satisfy the course's hard requirement for an actual PR. Credential values were held in memory and were never printed, persisted, or added to the repository.
- **Human approval:** managed approvals were obtained separately for adding `origin`, pushing the feature branch, publishing `main`, changing the default branch, and creating the PR.
- **Pull Request:** `https://github.com/TianMingYo/Camp_Harness/pull/1`, title `Build deterministic coding-agent feedback harness`, state `open`, base `main`, head `feature/feedback-loop-harness`; the controller did not merge it.
- **Initial remote verification:** GitHub Actions pull-request run `31474098931` and push run `31471299922` both completed with conclusion `success`; the PR reported mergeable state `clean` at head `dff22bd`.
- **TDD applicability:** Task 2 changed remote Git metadata and this audit document only; it introduced no product behavior or implementation code, so no additional RED/GREEN product test was applicable. The previously TDD-developed workflow contract and complete local suite remained the delivery gate.
- **Remaining external gates:** a public WebUI deployment URL and the student's own `REFLECTION.md` are still required by the course and are not fabricated by the agent.

## 2026-08-11 - Render public deployment and tested-image delivery

- **Mutation rationale:** the stronger delivery contracts fail if the Render Blueprint is absent
  or targets the wrong repository, branch, plan, region, health path, Docker context, or checks-pass
  trigger; if the Docker image loses its OCI source label or stops honoring the runtime `PORT`; or
  if GitHub Actions weakens read-only defaults, skips the dynamic-port smoke, publishes before
  quality succeeds, publishes on pull requests or other branches, changes the one-day artifact,
  or tags and pushes an image other than the tested artifact.
- **RED command:** `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_render_delivery.py tests/demo/test_github_delivery.py -q`
- **RED result:** `4 failed in 0.19s`. The Render test raised `FileNotFoundError` for absent
  `render.yaml`; the Docker contract reported the missing OCI source label; the quality contract
  raised `KeyError: 'permissions'`; and the publication contract raised `KeyError: 'publish'`.
  These failures were observed before any production configuration was changed.
- **Focused GREEN command:** `C:\Users\13900\anaconda3\python.exe -m pytest tests/demo/test_render_delivery.py tests/demo/test_github_delivery.py -q`
- **Focused GREEN result:** `4 passed in 0.05s`.
- **Full regression command/result:** `C:\Users\13900\anaconda3\python.exe -m pytest -q` ->
  `144 passed, 1 skipped, 1 warning in 23.45s`. The skip is the documented Windows symbolic-link
  privilege case; the warning is Starlette TestClient's httpx deprecation notice.
- **Ruff command/result:** `ruff check src tests demo` -> `All checks passed!`.
- **Compile command/result:** `C:\Users\13900\anaconda3\python.exe -m compileall -q src demo tests`
  exited `0` with no output.
- **Demo command/result:** `C:\Users\13900\anaconda3\python.exe -m demo.scenario` ->
  `corrected_after_feedback=true`, `policy_blocked=true`, `used_network=false`, and
  `final_state=succeeded`.
- **Diff command/result:** `git diff --check` exited `0`; Git emitted only expected Windows
  LF-to-CRLF working-copy notices.
- **Docker-local limitation:** `docker version` failed because `docker` is not installed or not on
  `PATH` in this environment. No local image build/container smoke was fabricated; the checked-in
  workflow performs both on GitHub's Ubuntu runner before saving the artifact.
- **External-action boundary:** no push, GitHub or Render API call, GHCR visibility change, or cloud
  service creation was performed by this task.
- **Self-review:** permissions remain read-only except for the dependent publish job's package
  write scope; publication is restricted to pushes on `feature/feedback-loop-harness`; the publish
  job downloads the one-day artifact produced only after the quality job builds and smokes the
  image. No Critical, Important, or Minor issue was found in the implementation diff.
- **Reviewer handoff:** independently review the complete range from
  `da9644aa8e969322844ad8900cd75559b1808569` through the task commit, including the exact contracts
  in `tests/demo/test_render_delivery.py` and `tests/demo/test_github_delivery.py`. Overall task
  acceptance remains pending that independent approval.
## 2026-08-12 - Aliyun VPS public deployment

- **Approved platform deviation:** Render account activation required payment-card verification. The student selected a rented Aliyun VPS instead, which is explicitly allowed by the course cloud-deployment requirement. The Render Blueprint remains checked in as an optional template; the actual delivery URL is the verified VPS URL below.
- **Plan:** `docs/superpowers/plans/2026-08-12-aliyun-vps-deployment.md`, initially committed as `929d59f`; the active plan was corrected after smoke diagnosis to match the existing homepage contract.
- **SSH boundary:** the controller used the student-supplied public IP and root account through a dedicated local PEM copy with a restricted ACL. No private-key contents, server password, or provider credential entered the repository, logs, or command output. The server host key was pinned in the ignored SDD workspace. Windows OpenSSH required `KexAlgorithms=curve25519-sha256` because the local 9.5 client did not support the server's first `sntrup761...` KEX offer.
- **Preflight:** Ubuntu `24.04.4 LTS`, `x86_64`, root, about `1.6 GB` RAM, `35 GB` free disk, Docker `29.1.3` already installed and active, no existing project container, TCP 80 initially free, UFW inactive.
- **Approved external mutations:** Docker installation had already been approved and completed by the student; container start was separately approved by the student; the student opened Aliyun security-group inbound TCP 80 from `0.0.0.0/0`. No SSH rule was broadened and no unrelated container or process was changed.
- **Image delivery:** anonymous GHCR `latest` manifest returned HTTP `200` with digest `sha256:c51472d590a14f62c01a5143b43732e0130f83c8aeb9f7f86a368d065726d00f`. The first remote pull exceeded the local 124-second SSH command limit after partial layer caching; read-only diagnostics showed GHCR DNS/HTTPS healthy and no orphaned pull. A single retried pull with a 600-second remote timeout completed with the exact digest.
- **Container:** image was started as `feedbackloop-harness` with `--restart unless-stopped` and `-p 80:8000`. Inspection reported `running`, restart policy `unless-stopped`, and `8000/tcp -> 0.0.0.0:80` plus IPv6 port mapping. Server-local HTTP returned `200`; Uvicorn reported `0.0.0.0:8000`.
- **Public smoke RED:** the first controller probe correctly reached the public service but failed only because the plan asserted the absent phrase `Feedback Loop Harness`. Source inspection confirmed the actual stable UI contract is `<h1>Feedback Loop</h1>` in `src/feedbackloop/api.py` and `src/feedbackloop/web/index.html`. No product code was changed; the verification contract was corrected and this deviation is recorded here.
- **Public smoke GREEN:** `http://121.40.246.197/` returned root `200` with `<h1>Feedback Loop</h1>`; `/demo/scenario` returned `{"mode":"mock","repository":"embedded-sample","iterations":["test_failure","pass"],"approval":"delete_requires_approval"}`; credential write returned `403` without echoing `deployment-probe-must-not-echo`; local repository task returned `400` with detail `public demo does not accept local repository paths`.
- **TDD applicability:** VPS installation, security-group metadata, image pull/run, public probes, and documentation record external state or factual delivery evidence only; they add no product behavior, so no fabricated product RED/GREEN cycle was introduced. The smoke-contract correction retained a failing diagnostic probe before the corrected passing probe.
- **Documentation-head automation:** commit `39c89ff179e1bc90a72d8cb175d2afa2da14c9e4` passed pull-request run `31525122839` and push run `31525119576`. Both quality jobs passed Docker build and dynamic-port smoke; the PR publish job was skipped; the push artifact save/upload, load, login, and publish steps all passed.
- **Post-documentation registry check:** anonymous `latest` returned HTTP `200` with digest `sha256:30119f00762d25891af62fbc23569aac2c376f16f7fa0f2c9233eb62e8460f0e`; the VPS still ran the previously verified `sha256:c51472d590a14f62c01a5143b43732e0130f83c8aeb9f7f86a368d065726d00f`. README records the stable public `:latest` reference instead of embedding a digest that would change README, retrigger the image build, and immediately become stale.
- **Remaining delivery gates:** publish the stable-reference documentation head, refresh the VPS to its resulting public `latest` digest after explicit replacement approval, rerun the public smoke, record the final immutable digest, update Pull Request #1 without merging, and leave `REFLECTION.md` student-authored.
