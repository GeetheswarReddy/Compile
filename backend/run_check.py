"""Run & Check Lambda handler.

The handler keeps execution, persistence, and the first-attempt scoring rule at
this boundary.  Repository instances are supplied by the composition root in
``context`` (a mapping or an object with matching attributes), which keeps the
module easy to test without constructing AWS clients at import time.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .contracts import MasteryState, SubmissionVerdict, serialize_mastery_state, serialize_verdict
from .execution_runner import run_submission
from .quota import consume_execution_quota


def _response(status_code: int, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(dict(payload or {})),
    }


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("body", {})
    if raw in (None, ""):
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        raise ValueError("body must be a JSON object")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("body must be a JSON object")
    return value


def _learner_id(event: Mapping[str, Any]) -> str:
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == "x-learner-id":
            if isinstance(value, str) and value.strip():
                return value
            break
    value = event.get("learnerId")
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError("X-Learner-Id is required")


def _dependency(context: Any, *names: str) -> Any:
    sources = [context]
    if isinstance(context, Mapping):
        sources.insert(0, context.get("repositories", {}))
        sources.insert(0, context.get("deps", {}))
    for source in sources:
        for name in names:
            if isinstance(source, Mapping) and name in source:
                return source[name]
            if source is not None and hasattr(source, name):
                return getattr(source, name)
    raise RuntimeError(f"missing dependency: {names[0]}")


def _mastery_after(mastery_repo: Any, learner_id: str, question: Any, passed: bool) -> MasteryState:
    current = mastery_repo.get(learner_id, question.topic)
    score = current.score if current is not None else question.difficulty
    next_score = max(1, min(10, score + (1 if passed else -1)))
    confidence = current.confidence if current is not None else 1.0
    return mastery_repo.save(MasteryState(learner_id, question.topic, next_score, confidence))


def run_check(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    """Evaluate one submission and score only the first attempt for a question."""
    try:
        body = _body(event)
        learner_id = _learner_id(event)
        question_id = body.get("questionId") or event.get("questionId")
        code = body.get("code")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("questionId is required")
        if not isinstance(code, str):
            raise ValueError("code is required")

        learner_repo = _dependency(context, "learner_repository", "learners")
        question_repo = _dependency(context, "question_repository", "questions")
        attempt_repo = _dependency(context, "attempt_repository", "attempts")
        mastery_repo = _dependency(context, "mastery_repository", "mastery")
        trace_repo = _dependency(context, "trace_repository", "trace")
        question = question_repo.get(question_id)
        if question is None:
            return _response(404, {"error": "question not found"})
        demo_quota = _dependency(context, "demo_quota", "demo", "quota")
        if not consume_execution_quota(learner_repo, learner_id, demo_quota):
            return _response(429, {"error": "execution quota exhausted"})

        verdict = run_submission(question, code)
        scored = attempt_repo.put_scored_attempt(
            learner_id,
            question_id,
            verdict,
            scoredAt=datetime.now(timezone.utc).isoformat(),
        )
        mastery = mastery_repo.get(learner_id, question.topic)
        if scored:
            mastery = _mastery_after(mastery_repo, learner_id, question, verdict.passed)

        # A run has no generation retries; retaining the field makes trace
        # records uniform with generated-question traces.
        trace_repo.append(learner_id, {
            "questionId": question_id,
            "provenance": question.provenance.value,
            "retries": 0,
            "retryCount": 0,
            "mastery": mastery.score if mastery is not None else None,
            "masterySnapshot": serialize_mastery_state(mastery) if mastery is not None else None,
            "scored": scored,
        })
        return _response(200, {
            "verdict": serialize_verdict(verdict),
            "scored": scored,
            "mastery": serialize_mastery_state(mastery) if mastery is not None else None,
        })
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc)})


__all__ = ["run_check"]
