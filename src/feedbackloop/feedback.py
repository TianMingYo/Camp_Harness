from __future__ import annotations

import re

from feedbackloop.models import CommandResult, Feedback, FeedbackKind


_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret)\s*[:=]\s*[^\s,;]+"
)


def redact_and_truncate(text: str, max_chars: int) -> str:
    if max_chars < 0:
        raise ValueError("max_chars must not be negative")
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", text)
    redacted = _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)
    if len(redacted) <= max_chars:
        return redacted
    suffix = "[truncated]"
    if max_chars <= len(suffix):
        return suffix[:max_chars]
    return redacted[: max_chars - len(suffix)] + suffix


class FeedbackClassifier:
    _FAILURE_KINDS = {
        "test": FeedbackKind.TEST_FAILURE,
        "build": FeedbackKind.BUILD_FAILURE,
        "lint": FeedbackKind.LINT_FAILURE,
        "type": FeedbackKind.TYPE_FAILURE,
        "policy": FeedbackKind.POLICY_BLOCKED,
    }

    def __init__(self, *, max_summary_chars: int = 4_000) -> None:
        if max_summary_chars < 1:
            raise ValueError("max_summary_chars must be positive")
        self.max_summary_chars = max_summary_chars

    def classify(
        self, result: CommandResult, before: str, after: str
    ) -> Feedback:
        del before, after
        summary = self._summary(result)
        if result.timed_out:
            kind = FeedbackKind.TIMEOUT
        elif result.kind == "policy":
            kind = FeedbackKind.POLICY_BLOCKED
        elif result.error is not None or result.exit_code is None:
            kind = FeedbackKind.COMMAND_ERROR
        elif result.exit_code == 0:
            kind = FeedbackKind.PASS
        else:
            kind = self._FAILURE_KINDS.get(result.kind, FeedbackKind.COMMAND_ERROR)
        return Feedback(kind=kind, exit_code=result.exit_code, summary=summary)

    def _summary(self, result: CommandResult) -> str:
        parts = [part for part in (result.error, result.stdout, result.stderr) if part]
        return redact_and_truncate("\n".join(parts), self.max_summary_chars)


class ProgressTracker:
    def changed(
        self,
        before: str,
        after: str,
        previous_feedback: Feedback | None,
    ) -> bool:
        del previous_feedback
        return before != after
