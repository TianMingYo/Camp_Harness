from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from feedbackloop.context import ContextBuilder, Plan
from feedbackloop.credentials import CredentialService
from feedbackloop.executor import LocalExecutor, command_text
from feedbackloop.feedback import FeedbackClassifier
from feedbackloop.llm import OpenAICompatibleClient
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import (
    ApprovalDecision,
    Task,
    TaskEvent,
    TaskState,
    ValidationCommand,
)
from feedbackloop.policy import PolicyEngine
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


class CredentialRequest(BaseModel):
    key: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    decision: ApprovalDecision


def build_local_loop(
    task: Task, task_store: Store, credential_service: CredentialService
) -> FeedbackLoop:
    if not task.provider or not task.base_url or not task.model:
        raise ValueError("provider, base_url and model are required for local execution")
    workspace = Workspace(Path(task.repo_root))
    executor = LocalExecutor(
        workspace,
        validation_commands=task.validation_commands,
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
            declared_commands={command_text(item) for item in task.validation_commands}
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


def create_app(
    *,
    store: Store | None = None,
    loop: FeedbackLoop | None = None,
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
    def create_task(request: TaskCreateRequest):
        if public_demo and request.repo_root:
            raise HTTPException(400, "public demo does not accept local repository paths")
        try:
            repo = Workspace(Path(request.repo_root)).resolve_repo()
        except InvalidRepositoryError as error:
            raise HTTPException(400, str(error)) from error
        detected = ValidationDetector.detect(repo)
        task = Task.create(
            repo_root=str(repo),
            request=request.request,
            provider=request.provider,
            base_url=request.base_url,
            model=request.model,
            validation_commands=tuple(
                ValidationDetector.apply_overrides(detected, request.validation_commands)
            ),
            max_iterations=request.max_iterations,
        )
        task_store.create_task(task)
        task_store.save_plan(task.id, Plan(summary=request.request))
        state = TaskStateMachine(task.state).transition(TaskEvent.PLAN_READY)
        task = task.model_copy(update={"state": state})
        task_store.update_task(task)
        return task.model_dump(mode="json")

    @app.post("/tasks/{task_id}/plan/approve", status_code=status.HTTP_202_ACCEPTED)
    def approve_plan(task_id: str, background_tasks: BackgroundTasks):
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
        task = task_store.get_task(task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        plan = task_store.get_plan(task_id)
        return {
            "task": task.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json") if plan else None,
            "iterations": [item.model_dump(mode="json") for item in task_store.list_iterations(task_id)],
            "approvals": [
                item.model_dump(mode="json")
                for item in task_store.list_approvals(task_id)
            ],
        }

    @app.post("/approvals/{approval_id}")
    def resolve_approval(
        approval_id: str,
        request: ApprovalRequest,
        background_tasks: BackgroundTasks,
    ):
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
demo_app = create_app(demo=True, public_demo=True)
