from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from feedbackloop.credentials import CredentialService
from feedbackloop.context import Plan
from feedbackloop.loop import FeedbackLoop
from feedbackloop.models import ApprovalDecision, Task, TaskState
from feedbackloop.store import Store
from feedbackloop.workspace import InvalidRepositoryError, Workspace
from feedbackloop.validation import ValidationDetector


class TaskCreateRequest(BaseModel):
    repo_root: str = Field(min_length=1)
    request: str = Field(min_length=1)
    max_iterations: int = Field(default=5, ge=1, le=100)


class CredentialRequest(BaseModel):
    key: str = Field(min_length=1)


class ApprovalRequest(BaseModel):
    decision: ApprovalDecision


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
        task = Task.create(
            repo_root=str(repo),
            request=request.request,
            validation_commands=tuple(ValidationDetector.detect(repo)),
            max_iterations=request.max_iterations,
        )
        task_store.create_task(task)
        task_store.save_plan(task.id, Plan(summary=request.request))
        return task.model_dump(mode="json")

    @app.post("/tasks/{task_id}/plan/approve", status_code=status.HTTP_202_ACCEPTED)
    def approve_plan(task_id: str, background_tasks: BackgroundTasks):
        if loop is None:
            raise HTTPException(503, "loop service is not configured")
        try:
            state = loop.approve_plan(task_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        background_tasks.add_task(loop.run, task_id)
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
        }

    @app.post("/approvals/{approval_id}")
    def resolve_approval(approval_id: str, request: ApprovalRequest):
        if loop is None:
            raise HTTPException(503, "loop service is not configured")
        try:
            state = loop.resolve_approval(approval_id, request.decision)
        except (KeyError, ValueError) as error:
            raise HTTPException(400, str(error)) from error
        return {"approval_id": approval_id, "state": state.value}

    @app.post("/providers/{provider}/credentials")
    def set_credentials(provider: str, request: CredentialRequest):
        credential_service.set(provider, request.key)
        return credential_service.status(provider).model_dump()

    @app.delete("/providers/{provider}/credentials")
    def clear_credentials(provider: str):
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
