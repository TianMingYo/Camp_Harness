import pytest

from feedbackloop.feedback import FeedbackClassifier, ProgressTracker, redact_and_truncate
from feedbackloop.models import CommandResult, Feedback, FeedbackKind


def result(**values) -> CommandResult:
    defaults = dict(kind="test", exit_code=1, stdout="", stderr="")
    defaults.update(values)
    return CommandResult(**defaults)


def test_nonzero_test_result_is_test_failure():
    feedback = FeedbackClassifier().classify(
        result(stdout="FAILED test_greeting"), "before", "after"
    )
    assert feedback.kind is FeedbackKind.TEST_FAILURE


@pytest.mark.parametrize(
    ("command_kind", "expected"),
    [
        ("build", FeedbackKind.BUILD_FAILURE),
        ("lint", FeedbackKind.LINT_FAILURE),
        ("type", FeedbackKind.TYPE_FAILURE),
        ("policy", FeedbackKind.POLICY_BLOCKED),
    ],
)
def test_nonzero_result_uses_explicit_command_kind(command_kind, expected):
    feedback = FeedbackClassifier().classify(result(kind=command_kind), "a", "b")
    assert feedback.kind is expected


def test_timeout_and_start_error_take_priority():
    classifier = FeedbackClassifier()
    assert classifier.classify(result(timed_out=True, error="timeout"), "a", "b").kind is FeedbackKind.TIMEOUT
    assert classifier.classify(result(exit_code=None, error="missing"), "a", "b").kind is FeedbackKind.COMMAND_ERROR


def test_policy_result_takes_priority_over_command_error():
    feedback = FeedbackClassifier().classify(
        result(kind="policy", exit_code=None, error="blocked"), "a", "a"
    )
    assert feedback.kind is FeedbackKind.POLICY_BLOCKED


def test_zero_exit_is_pass():
    feedback = FeedbackClassifier().classify(result(exit_code=0), "same", "same")
    assert feedback.kind is FeedbackKind.PASS


def test_unknown_nonzero_is_command_error():
    feedback = FeedbackClassifier().classify(result(kind="custom"), "a", "b")
    assert feedback.kind is FeedbackKind.COMMAND_ERROR


def test_equal_workspace_and_feedback_is_no_progress():
    tracker = ProgressTracker()
    previous = Feedback(kind=FeedbackKind.TEST_FAILURE)
    assert tracker.changed("same", "same", previous) is False
    assert tracker.changed("before", "after", previous) is True


def test_redaction_happens_before_truncation():
    text = "Authorization: Bearer very-secret-token API_KEY=also-secret " + "x" * 100
    redacted = redact_and_truncate(text, 70)
    assert "very-secret-token" not in redacted
    assert "also-secret" not in redacted
    assert len(redacted) <= 70
    assert redacted.endswith("[truncated]")
