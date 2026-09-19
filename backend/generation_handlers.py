"""Bedrock candidate generation and verified-candidate handling."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from .contracts import PreparedQuestion, Provenance, Question, TestCase, Topic
from .execution_client import verify_question

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
        return _candidate_value(value)
    if isinstance(candidate, Mapping):
        topic = candidate.get("topic")
        tests = candidate.get("hiddenTests", candidate.get("hidden_tests"))
        if isinstance(topic, str):
            topic = Topic(topic)
        if not isinstance(tests, (list, tuple)):
            raise ValueError("candidate hiddenTests are required")
        hidden = tuple(
            test if isinstance(test, TestCase) else TestCase(test.get("input_data", test.get("input")), test.get("expected_output", test.get("expected")), test.get("positional", "input" in test))
            for test in tests
        )
        return Question(
            question_id="generated-" + str(uuid4()),
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

    Verification continues after the browser fallback deadline. A candidate
    outside the current mastery range is discarded without a failure increment.  ``event`` may contain the candidate
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
    if event.get("stale") is True:
        return {"status": "stale", "discarded": True}
    if verifier is verify_question:
        from .dependencies import compose_dependencies
        deps = compose_dependencies()
        mastery_repository = mastery_repository or deps["mastery_repository"]
        question_repository = question_repository or deps["question_repository"]
        prepared_repository = prepared_repository or deps["prepared_repository"]
        if not deps["demo_quota"].consume():
            return {**dict(event), "status": "stale", "discarded": True}
    candidate = event.get("candidate", event.get("question"))
    try:
        question = _candidate_value(candidate)
        if mastery_repository is not None:
            mastery = mastery_repository.get(learner_id, topic)
            if mastery and abs(question.difficulty - mastery.score) > 1:
                return {**dict(event), "status": "stale", "discarded": True}
        if question_repository is not None:
            from .question_select import _all
            prior = _all(question_repository)
            if any(q.prompt.strip().lower() == question.prompt.strip().lower() or q.reference_solution.strip() == question.reference_solution.strip() for q in prior):
                raise ValueError("candidate duplicates an existing question")
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
    from dataclasses import replace
    question = replace(question, verification_retries=max(0, int(event.get("attempt", 1)) - 1))
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
    from .dependencies import compose_dependencies
    from .question_select import _all
    corpus = _all(compose_dependencies()["question_repository"])
    references = [{"prompt": q.prompt, "difficulty": q.difficulty} for q in corpus if q.topic.value == event.get("topic")]
    response = bedrock_client.converse(
        modelId=model_id,
        inferenceConfig={"maxTokens": 2500, "temperature": 0.7},
        system=[{"text": "Return only a JSON coding-question object with topic, integer difficulty (1-10), prompt, starterCode, hiddenTests, and referenceSolution. Use the exact requested topic and mastery as difficulty. Include a named Python function with typed parameters and return type in starterCode. Describe constraints and examples in prompt. Include 2 or 3 hiddenTests, each with input (a list of positional arguments; wrap a single list argument in another list) and expected_output. ReferenceSolution must implement the named function. Create a materially different exercise from the supplied existing prompts. No markdown fences."}],
        messages=[{"role": "user", "content": [{"text": json.dumps({"topic": event.get("topic"), "mastery": event.get("mastery"), "existingQuestions": references})}]}],
    )
    text = "".join(item.get("text", "") for item in response.get("output", {}).get("message", {}).get("content", []))
    return {**dict(event), "candidate": json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())}


__all__ = ["PREPARED_TTL", "generate_candidate", "handle_generated_candidate"]
