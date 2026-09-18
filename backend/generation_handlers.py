"""Bedrock candidate generation and verified-candidate handling."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from .contracts import PreparedQuestion, Provenance, Question, TestCase, Topic
from .execution_runner import verify_question

PREPARED_TTL = timedelta(minutes=30)


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current


def _candidate_value(candidate: Any) -> Any:
    if isinstance(candidate, Question):
        return candidate
    if isinstance(candidate, Mapping) and "question" in candidate:
        return _candidate_value(candidate["question"])
    if isinstance(candidate, str):
        value = json.loads(candidate)
        return value
    if isinstance(candidate, Mapping):
        topic = candidate.get("topic")
        tests = candidate.get("hiddenTests", candidate.get("hidden_tests"))
        if isinstance(topic, str):
            topic = Topic(topic)
        if not isinstance(tests, (list, tuple)):
            raise ValueError("candidate hiddenTests are required")
        hidden = tuple(
            test if isinstance(test, TestCase) else TestCase(test.get("input_data", test.get("input")), test.get("expected_output", test.get("expected")))
            for test in tests
        )
        return Question(
            question_id=candidate.get("questionId", candidate.get("question_id", str(uuid4()))),
            topic=topic,
            difficulty=int(candidate["difficulty"]),
            prompt=candidate["prompt"],
            starter_code=candidate.get("starterCode", candidate.get("starter_code", "")),
            hidden_tests=hidden,
            reference_solution=candidate.get("referenceSolution", candidate.get("reference_solution", "")),
            provenance=Provenance.GENERATED,
        )
    raise ValueError("candidate must be a Question or JSON object")


def _fallback(learner_id: str, topic: Topic, mastery_repo: Any, question_repo: Any) -> dict[str, Any]:
    if mastery_repo is None or not hasattr(mastery_repo, "increment_generation_failure"):
        raise RuntimeError("mastery_repository.increment_generation_failure is required")
    mastery_repo.increment_generation_failure(learner_id, topic)
    mastery = mastery_repo.get(learner_id, topic) if mastery_repo is not None else None
    score = mastery.score if mastery is not None else 1
    if hasattr(question_repo, "all"):
        questions = question_repo.all()
    elif hasattr(question_repo, "list"):
        questions = question_repo.list()
    else:
        from .repositories import _question_from_item
        questions = [_question_from_item(item) for item in question_repo.table.scan().get("Items", [])]
    eligible = [q for q in questions if q.topic is topic and q.provenance in (Provenance.SEEDED, Provenance.CURATED)]
    if not eligible:
        raise LookupError("no curated fallback question exists")
    question = min(eligible, key=lambda q: (abs(q.difficulty - score), q.question_id))
    return {"status": "fallback", "questionId": question.question_id, "provenance": question.provenance.value}


def handle_generated_candidate(
    event: Mapping[str, Any] | Any,
    context: Any = None,
    prepared_repository: Any | None = None,
    question_repository: Any | None = None,
    mastery_repository: Any | None = None,
    verifier: Any = verify_question,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify one candidate, persist it separately, or return a fallback.

    A candidate whose generation deadline has elapsed is discarded and does
    not increment the failure counter.  ``event`` may contain the candidate
    directly or under ``candidate``/``question``; this accommodates the
    Bedrock task's compact output and direct unit-test calls.
    """
    del context
    if not isinstance(event, Mapping):
        event = {"candidate": event}
    learner_id = event.get("learnerId")
    topic = event.get("topic")
    topic = topic if isinstance(topic, Topic) else Topic(topic)
    if not isinstance(learner_id, str) or not learner_id.strip():
        raise ValueError("learnerId is required")
    current = _now(now)
    if event.get("fallback") is True:
        if question_repository is None or mastery_repository is None:
            from .dependencies import compose_dependencies
            deps = compose_dependencies()
            question_repository = question_repository or deps["question_repository"]
            mastery_repository = mastery_repository or deps["mastery_repository"]
        return _fallback(learner_id, topic, mastery_repository, question_repository)
    deadline = event.get("deadline") or event.get("generationDeadline")
    if isinstance(deadline, str):
        deadline = datetime.fromisoformat(deadline)
    if event.get("stale") is True or (deadline is not None and current >= deadline):
        return {"status": "stale", "discarded": True}
    candidate = event.get("candidate", event.get("question"))
    try:
        question = _candidate_value(candidate)
        if question.topic is not topic or not verifier(question):
            raise ValueError("candidate failed verification")
    except Exception:
        attempt_state = event.get("attemptState") or {}
        attempt = int(event.get("attempt", attempt_state.get("attempt", 1)))
        if attempt < 3:
            return {**dict(event), "status": "retry", "attempt": attempt}
        if question_repository is None or mastery_repository is None:
            from .dependencies import compose_dependencies
            deps = compose_dependencies()
            question_repository = question_repository or deps["question_repository"]
            mastery_repository = mastery_repository or deps["mastery_repository"]
        return _fallback(learner_id, topic, mastery_repository, question_repository)
    if prepared_repository is None:
        from .dependencies import compose_dependencies
        prepared_repository = compose_dependencies()["prepared_repository"]
    expires_at = current + PREPARED_TTL
    prepared_repository.save(PreparedQuestion(learner_id, topic, question, expires_at))
    return {"status": "accepted", "questionId": question.question_id, "expiresAt": expires_at.isoformat()}


def generate_candidate(event: Mapping[str, Any], context: Any = None, *, bedrock_client: Any | None = None) -> dict[str, Any]:
    """Invoke Bedrock Converse and return its JSON candidate payload."""
    del context
    if bedrock_client is None:
        import boto3  # pragma: no cover - supplied by Lambda
        bedrock_client = boto3.client("bedrock-runtime")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if not model_id:
        raise RuntimeError("BEDROCK_MODEL_ID is not configured")
    response = bedrock_client.converse(
        modelId=model_id,
        system=[{"text": "Return only one JSON coding-question object with questionId, topic, difficulty, prompt, starterCode, hiddenTests, and referenceSolution."}],
        messages=[{"role": "user", "content": [{"text": json.dumps({"topic": event.get("topic"), "mastery": event.get("mastery")})}]}],
    )
    text = "".join(item.get("text", "") for item in response.get("output", {}).get("message", {}).get("content", []))
    return {**dict(event), "candidate": json.loads(text)}


__all__ = ["PREPARED_TTL", "generate_candidate", "handle_generated_candidate"]
