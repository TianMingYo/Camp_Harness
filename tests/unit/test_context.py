from feedbackloop.context import ContextBuilder, FileSummary, Plan
from feedbackloop.models import Feedback, FeedbackKind, IterationRecord, Task


def record(number: int) -> IterationRecord:
    return IterationRecord(
        task_id="task",
        number=number,
        workspace_fingerprint=str(number),
        feedback=Feedback(kind=FeedbackKind.TEST_FAILURE, summary=f"failure {number}"),
    )


def test_context_is_bounded_to_recent_feedback():
    context = ContextBuilder(max_recent_iterations=2).build(
        Task.create(repo_root="/repo", request="feature"),
        Plan(summary="plan"),
        [record(1), record(2), record(3)],
        [FileSummary(path="app.py", summary="main module")],
    )
    assert [item.number for item in context.recent_iterations] == [2, 3]


def test_context_excludes_sensitive_files_and_bounds_summary():
    context = ContextBuilder(max_file_summary_chars=20).build(
        Task.create(repo_root="/repo", request="feature"),
        Plan(summary="plan"),
        [],
        [
            FileSummary(path=".env", summary="API_KEY=secret"),
            FileSummary(path="src/app.py", summary="x" * 100),
        ],
    )
    assert [file.path for file in context.files] == ["src/app.py"]
    assert len(context.files[0].summary) <= 20
