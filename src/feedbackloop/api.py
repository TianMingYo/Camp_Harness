from __future__ import annotations

import tempfile
import subprocess
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from feedbackloop.context import ContextBuilder
from feedbackloop.credentials import CredentialService
from feedbackloop.executor import LocalExecutor, command_text
from feedbackloop.feedback import FeedbackClassifier, redact_and_truncate
from feedbackloop.llm import (
    InvalidLLMResponse,
    OpenAICompatibleClient,
    PlanGenerator,
    PlanningContext,
)
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import (
    Action,
    ApprovalDecision,
    ActionType,
    Task,
    TaskEvent,
    TaskState,
    ValidationCommand,
)
from feedbackloop.policy import DecisionKind, PolicyEngine
from feedbackloop.state import TaskStateMachine
from feedbackloop.store import Store
from feedbackloop.workspace import InvalidRepositoryError, Workspace
from feedbackloop.validation import ValidationDetector


class TaskCreateRequest(BaseModel):
    repo_root: str = Field(min_length=1)
    request: str = Field(min_length=1)
    max_iterations: int = Field(default=5, ge=1, le=100)
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    validation_commands: tuple[ValidationCommand, ...] | None = None
    plan_files: tuple[str, ...] = ()


class CredentialRequest(BaseModel):
    key: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    decision: ApprovalDecision


def build_local_loop(
    task: Task, task_store: Store, credential_service: CredentialService
) -> FeedbackLoop:
    if not task.provider or not task.base_url or not task.model:
        raise ValueError("provider, base_url and model are required for local execution")
    plan = task_store.get_plan(task.id)
    if plan is None:
        raise ValueError("task has no plan")
    workspace = Workspace(Path(task.repo_root))
    executor = LocalExecutor(
        workspace,
        validation_commands=task.validation_commands,
        summary_paths=plan.files,
    )
    return FeedbackLoop(
        task_store=task_store,
        llm=OpenAICompatibleClient(
            base_url=task.base_url,
            model=task.model,
            provider=task.provider,
            credential_provider=credential_service.build_provider(task.provider),
        ),
        policy=PolicyEngine(
            declared_commands={command_text(item) for item in task.validation_commands},
            allowed_paths=plan.files,
            unsupported_actions={ActionType.NETWORK, ActionType.GIT_PUSH},
            undeclared_commands_require_approval=False,
        ),
        executor=executor,
        classifier=FeedbackClassifier(),
        context_builder=ContextBuilder(),
        max_iterations=task.max_iterations,
    )


def _task_for_approval(task_store: Store, approval_id: str) -> Task | None:
    approval = task_store.get_approval_by_id(approval_id)
    if approval is None:
        return None
    action = task_store.get_action(approval.action_id)
    if action is None or action.iteration_id is None:
        return None
    iteration = task_store.get_iteration(action.iteration_id)
    if iteration is None:
        return None
    return task_store.get_task(iteration.task_id)


def _normalize_plan_files(workspace: Workspace, paths: tuple[str, ...]) -> tuple[str, ...]:
    root = workspace.resolve_repo()
    normalized: list[str] = []
    for value in paths:
        if not value.strip() or Path(value).is_absolute():
            raise ValueError("plan files must be non-empty repository-relative paths")
        resolved = workspace.resolve_child(value)
        relative = resolved.relative_to(root).as_posix()
        decision = PolicyEngine().check(Action.read(relative), workspace)
        if decision.kind is DecisionKind.DENY:
            raise ValueError(decision.reason)
        if relative not in normalized:
            normalized.append(relative)
    return tuple(normalized)


def _repository_summary(repo: Path) -> str:
    manifests = (
        "AGENTS.md",
        "Cargo.toml",
        "GEMINI.md",
        "package.json",
        "pyproject.toml",
        "README.md",
    )
    present = [name for name in manifests if (repo / name).is_file()]
    try:
        branch = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        ).stdout.strip()
        status_summary = subprocess.run(
            ["git", "-C", str(repo), "status", "--short"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        ).stdout.splitlines()[:20]
    except (OSError, subprocess.SubprocessError):
        branch = "unavailable"
        status_summary = []
    return (
        f"branch: {branch or 'detached'}\n"
        f"manifests: {', '.join(present) or 'none'}\n"
        f"status: {len(status_summary)} changed path(s)"
    )


def _generate_plan(
    *,
    task: Task,
    task_store: Store,
    workspace: Workspace,
    allowed_files: tuple[str, ...],
    validation_commands: tuple[ValidationCommand, ...],
    planner: PlanGenerator,
) -> None:
    command_list = tuple(command_text(item) for item in validation_commands)
    try:
        plan = planner.generate_plan(
            PlanningContext(
                task_request=task.request,
                repository_summary=_repository_summary(Path(task.repo_root)),
                allowed_files=allowed_files,
                validation_commands=command_list,
            )
        )
        normalized_files = _normalize_plan_files(workspace, plan.files)
        if not set(normalized_files).issubset(allowed_files):
            raise ValueError("generated plan exceeds the authorized file scope")
        if plan.validation_commands != command_list:
            raise ValueError("generated plan changed the configured validation commands")
        if plan.estimated_iterations > task.max_iterations:
            raise ValueError("generated plan exceeds the task iteration limit")
        plan = plan.model_copy(update={"files": normalized_files})
        task_store.save_plan(task.id, plan)
        state = TaskStateMachine(task.state).transition(TaskEvent.PLAN_READY)
        task_store.update_task(task.model_copy(update={"state": state}))
        task_store.append_audit_event(task.id, "plan_ready", {"state": state.value})
        task_store.append_audit_event(
            task.id,
            "state_transition",
            {"from": task.state.value, "to": state.value},
        )
    except Exception as error:
        state = TaskStateMachine(task.state).transition(TaskEvent.FAIL)
        task_store.update_task(task.model_copy(update={"state": state}))
        task_store.append_audit_event(
            task.id,
            "state_transition",
            {"from": task.state.value, "to": state.value},
        )
        raw_summary = (
            error.raw_content
            if isinstance(error, InvalidLLMResponse) and error.raw_content
            else str(error) or type(error).__name__
        )
        task_store.append_audit_event(
            task.id,
            "plan_generation_failed",
            {"summary": redact_and_truncate(raw_summary, 1_000)},
        )


def create_app(
    *,
    store: Store | None = None,
    loop: FeedbackLoop | None = None,
    planner: PlanGenerator | None = None,
    credentials: CredentialService | None = None,
    demo: bool = False,
    public_demo: bool = False,
) -> FastAPI:
    app = FastAPI(title="Feedback Loop Harness")
    task_store = store or Store(Path(".feedbackloop.sqlite3"))
    credential_service = credentials or CredentialService()
    web_root = Path(__file__).parent / "web"
    if web_root.is_dir():
        app.mount("/web", StaticFiles(directory=web_root), name="web")

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_file = web_root / "index.html"
        if index_file.is_file():
            return HTMLResponse(index_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Feedback Loop</h1>")

    @app.post("/tasks", status_code=status.HTTP_201_CREATED)
    def create_task(request: TaskCreateRequest, background_tasks: BackgroundTasks):
        if public_demo and request.repo_root:
            raise HTTPException(400, "public demo does not accept local repository paths")
        if not request.plan_files or "**" in request.plan_files:
            raise HTTPException(400, "explicit plan file paths are required")
        provider_ready = bool(request.provider and request.base_url and request.model)
        if planner is None and not provider_ready:
            message = (
                "provider, base_url and model are required for local execution"
                if loop is None
                else "planner or complete provider configuration is required"
            )
            raise HTTPException(400, message)
        try:
            workspace = Workspace(Path(request.repo_root))
            repo = workspace.resolve_repo()
            plan_files = _normalize_plan_files(workspace, request.plan_files)
        except (InvalidRepositoryError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        detected = ValidationDetector.detect(repo)
        validation_commands = ValidationDetector.apply_overrides(
            detected, request.validation_commands
        )
        if not validation_commands:
            raise HTTPException(400, "at least one validation command is required")
        try:
            ValidationDetector.preflight(validation_commands, repo)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        task = Task.create(
            repo_root=str(repo),
            request=request.request,
            provider=request.provider,
            base_url=request.base_url,
            model=request.model,
            validation_commands=tuple(validation_commands),
            max_iterations=request.max_iterations,
        )
        task_store.create_task(task)
        active_planner = planner
        if active_planner is None:
            if not (task.provider and task.base_url and task.model):
                raise HTTPException(400, "complete provider configuration is required")
            active_planner = OpenAICompatibleClient(
                base_url=task.base_url,
                model=task.model,
                provider=task.provider,
                credential_provider=credential_service.build_provider(task.provider),
            )
        background_tasks.add_task(
            _generate_plan,
            task=task,
            task_store=task_store,
            workspace=workspace,
            allowed_files=plan_files,
            validation_commands=tuple(validation_commands),
            planner=active_planner,
        )
        return task.model_dump(mode="json")

    @app.post("/tasks/{task_id}/plan/approve", status_code=status.HTTP_202_ACCEPTED)
    def approve_plan(task_id: str, background_tasks: BackgroundTasks):
        if public_demo:
            raise HTTPException(404, "task execution is unavailable in public demo")
        try:
            active_loop = loop
            if active_loop is None:
                task = task_store.get_task(task_id)
                if task is None:
                    raise KeyError(task_id)
                active_loop = build_local_loop(task, task_store, credential_service)
            state = active_loop.approve_plan(task_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        background_tasks.add_task(active_loop.run, task_id)
        return {"task_id": task_id, "state": state.value}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str):
        if public_demo:
            raise HTTPException(404, "task access is unavailable in public demo")
        task = task_store.get_task(task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        plan = task_store.get_plan(task_id)
        return {
            "task": task.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json") if plan else None,
            "iterations": [item.model_dump(mode="json") for item in task_store.list_iterations(task_id)],
            "audit_events": task_store.list_audit_events(task_id),
            "approvals": [
                {
                    "approval": item.model_dump(mode="json"),
                    "action": (
                        action.model_dump(mode="json")
                        if (action := task_store.get_action(item.action_id))
                        else None
                    ),
                }
                for item in task_store.list_approvals(task_id)
            ],
        }

    @app.post("/approvals/{approval_id}")
    def resolve_approval(
        approval_id: str,
        request: ApprovalRequest,
        background_tasks: BackgroundTasks,
    ):
        if public_demo:
            raise HTTPException(404, "approvals are unavailable in public demo")
        try:
            task = _task_for_approval(task_store, approval_id)
            active_loop = loop
            if active_loop is None:
                if task is None:
                    raise KeyError(approval_id)
                active_loop = build_local_loop(task, task_store, credential_service)
            state = active_loop.resolve_approval(approval_id, request.decision)
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        if state is TaskState.RUNNING and task is not None:
            background_tasks.add_task(active_loop.run, task.id)
        return {"approval_id": approval_id, "state": state.value}

    @app.post("/providers/{provider}/credentials")
    def set_credentials(provider: str, request: CredentialRequest):
        if public_demo:
            raise HTTPException(403, "public demo does not accept credentials")
        credential_service.set(provider, request.key)
        return credential_service.status(provider).model_dump()

    @app.get("/providers/{provider}/credentials")
    def credential_status(provider: str):
        if public_demo:
            raise HTTPException(403, "public demo does not expose credentials")
        return credential_service.status(provider).model_dump()

    @app.delete("/providers/{provider}/credentials")
    def clear_credentials(provider: str):
        if public_demo:
            raise HTTPException(403, "public demo does not manage credentials")
        credential_service.clear(provider)
        return credential_service.status(provider).model_dump()

    @app.get("/demo/scenario")
    def demo_scenario():
        if not demo:
            raise HTTPException(404, "demo mode is disabled")
        return {
            "mode": "mock",
            "repository": "embedded-sample",
            "iterations": ["test_failure", "pass"],
            "approval": "delete_requires_approval",
        }

    return app


app = create_app(demo=False)
demo_app = create_app(
    store=Store(Path(tempfile.mkdtemp(prefix="feedbackloop-public-demo-")) / "demo.sqlite3"),
    demo=True,
    public_demo=True,
)
