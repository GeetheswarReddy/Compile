"""API Gateway adapters.  Public responses are explicitly allow-listed."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping

from . import baseline, generation_orchestrator, hints, learner_state, question_select, reflection, run_check
from .contracts import Question, Topic, serialize_learner_state, serialize_question, serialize_verdict
from .dependencies import compose_dependencies
from .execution_client import run_submission
import logging

logger = logging.getLogger(__name__)

TOPIC_IDS = {
    "arrays": Topic.ARRAYS,
    "strings": Topic.STRINGS,
    "hash-maps-two-pointers": Topic.HASH_MAPS_TWO_POINTERS,
}
TOTAL_BASELINE_QUESTIONS = 5


from .http import response as _response


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or {}
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, Mapping):
        raise ValueError("body must be a JSON object")
    return dict(value)


def _learner_id(event: Mapping[str, Any], body: Mapping[str, Any] | None = None) -> str:
    headers = event.get("headers") or {}
    value = next((v for k, v in headers.items() if k.lower() == "x-learner-id"), None)
    value = value or (body or {}).get("learnerId") or event.get("learnerId")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("X-Learner-Id is required")
    return value


def _topic(event: Mapping[str, Any], body: Mapping[str, Any] | None = None) -> Topic:
    value = (event.get("pathParameters") or {}).get("topicId") or (body or {}).get("topic") or (body or {}).get("topicId")
    if value in TOPIC_IDS:
        return TOPIC_IDS[value]
    try:
        return Topic(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("topic is required and must be supported") from exc


def _public_question(question: Question | None) -> dict[str, Any] | None:
    return serialize_question(question) if question is not None else None


def _answered(deps, learner_id):
    return sum(deps["attempt_repository"].get(learner_id, q.question_id) is not None
        for q in baseline.baseline_questions(deps["question_repository"]))


def _stored_verdict(attempt: Mapping[str, Any]) -> dict[str, Any]:
    """Recreate the public verdict for an idempotent baseline retry."""

    return {
        "passed": bool(attempt.get("passed")),
        "failedCases": [
            {
                "input": item.get("input_data", item.get("input")),
                "expected": item.get("expected_output", item.get("expected")),
                "actual": item.get("actual_output", item.get("actual")),
            }
            for item in attempt.get("failedCases", [])[:2]
            if isinstance(item, Mapping)
        ],
    }


def _gate(deps, learner_id):
    learner = deps["learner_repository"].get(learner_id)
    if learner is None or not learner.baseline_completed:
        return _response(403, {"error": "Complete the baseline assessment first.", "baselineRequired": True})
    return None


def _state(deps, learner_id):
    learner = deps["learner_repository"].get(learner_id)
    quota = deps["demo_quota"]
    exhausted = quota.exhausted() if hasattr(quota, "exhausted") else False
    return {"learner": serialize_learner_state(learner) if learner else None,
            "readOnly": exhausted or bool(learner and (learner.run_check_actions >= 5 or learner.generation_requests >= 2))}


def _questions(repository: Any) -> list[Question]:
    if hasattr(repository, "all"):
        return list(repository.all())
    if hasattr(repository, "list"):
        return list(repository.list())
    from .repositories import _question_from_item
    return [_question_from_item(item) for item in repository.table.scan().get("Items", [])]


def _adapt(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return action()
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc)})
    except Exception:
        logger.exception("API request failed")
        return _response(500, {"error": "The service could not complete this request. Please retry."})


def init_learner(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    def action() -> dict[str, Any]:
        body, deps = _body(event), compose_dependencies()
        learner = learner_state.init_learner(deps["learner_repository"], _learner_id(event, body))
        return _response(200, {"learner": serialize_learner_state(learner)})
    return _adapt(action)


def baseline_next(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    def action() -> dict[str, Any]:
        deps, learner_id = compose_dependencies(), _learner_id(event)
        question = baseline.get_baseline_next(learner_id, deps["learner_repository"], deps["question_repository"], deps["attempt_repository"])
        learner = deps["learner_repository"].get(learner_id)
        return _response(200, {"completed": bool(learner and learner.baseline_completed), "question": _public_question(question), "progress": {"answered": _answered(deps, learner_id), "total": TOTAL_BASELINE_QUESTIONS}})
    return _adapt(action)


def baseline_submit(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    def action() -> dict[str, Any]:
        body, deps = _body(event), compose_dependencies()
        learner_id, question_id, code = _learner_id(event, body), body.get("questionId"), body.get("code")
        if not isinstance(question_id, str) or not isinstance(code, str):
            raise ValueError("questionId and code are required")
        question = deps["question_repository"].get(question_id)
        if question is None:
            return _response(404, {"error": "question not found"})
        current = baseline.get_baseline_next(learner_id, deps["learner_repository"], deps["question_repository"], deps["attempt_repository"])
        existing_attempt = deps["attempt_repository"].get(learner_id, question_id)
        if existing_attempt:
            learner = deps["learner_repository"].get(learner_id)
            return _response(200, {"completed": learner.baseline_completed, "question": _public_question(current), "verdict": _stored_verdict(existing_attempt), "progress": {"answered": _answered(deps, learner_id), "total": 5}})
        if current is None or current.question_id != question_id:
            return _response(400, {"error": "Submit the current baseline question."})
        if not deps["demo_quota"].consume():
            return _response(429, {"error": "Demo execution quota exhausted.", "readOnly": True})
        verdict = deps.get("executor", run_submission)(question, code)
        learner = baseline.submit_baseline(learner_id, question_id, verdict, deps["learner_repository"], deps["question_repository"], deps["attempt_repository"], deps["mastery_repository"])
        next_question = baseline.get_baseline_next(learner_id, deps["learner_repository"], deps["question_repository"], deps["attempt_repository"])
        return _response(200, {"completed": learner.baseline_completed, "question": _public_question(next_question), "verdict": serialize_verdict(verdict), "progress": {"answered": _answered(deps, learner_id), "total": TOTAL_BASELINE_QUESTIONS}})
    return _adapt(action)


def next_question(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    def action() -> dict[str, Any]:
        deps, learner_id, topic = compose_dependencies(), _learner_id(event), _topic(event)
        denied = _gate(deps, learner_id)
        if denied:
            return denied
        question = question_select.get_next_question(learner_id, topic, deps["mastery_repository"], deps["question_repository"], deps["attempt_repository"], deps["prepared_repository"])
        return _response(200, {"question": _public_question(question), "completed": question is None, **_state(deps, learner_id)})
    return _adapt(action)


def run_and_check(event, context):
    def action():
        deps, learner_id = compose_dependencies(), _learner_id(event)
        denied = _gate(deps, learner_id)
        if denied:
            return denied
        response = run_check.run_check(event, deps)
        payload = json.loads(response["body"])
        if response["statusCode"] != 200:
            return _response(response["statusCode"], {**payload, **_state(deps, learner_id)})
        return _response(200, {**payload["verdict"], "scored": payload["scored"], "mastery": payload["mastery"], **_state(deps, learner_id)})
    return _adapt(action)


def generate(event, context):
    def action():
        deps, body = compose_dependencies(), _body(event)
        learner_id, topic = _learner_id(event, body), _topic(event, body)
        denied = _gate(deps, learner_id)
        if denied:
            return denied
        available = [q for q in deps["question_repository"].for_learner(learner_id)
                     if q.topic is topic and not deps["attempt_repository"].get(learner_id, q.question_id)]
        if not available and not deps["prepared_repository"].get(learner_id, topic):
            return _response(200, {"question": None, "completed": True, **_state(deps, learner_id)})
        mastery = deps["mastery_repository"].get(learner_id, topic)
        normalized = {**event, "body": {"topic": topic.value, "mastery": mastery.score if mastery else 1}}
        result = generation_orchestrator.start_generation(normalized, None, learner_repository=deps["learner_repository"], demo_quota=deps["demo_quota"], step_functions_client=deps["step_functions_client"], state_machine_arn=os.environ.get("GENERATION_STATE_MACHINE_ARN"))
        return _response(result["statusCode"], {**json.loads(result["body"]), **_state(deps, learner_id)})
    return _adapt(action)


def next_hint(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    return hints.get_next_hint(event, compose_dependencies())


def create_reflection(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    deps = compose_dependencies()
    body = _body(event)
    if not deps["attempt_repository"].get(_learner_id(event), body.get("questionId", "")):
        return _response(403, {"error": "Check a solution before recording a reflection."})
    return reflection.create_reflection(event, None, repository=deps["reflection_repository"], s3=deps["s3"])


def delete_reflection(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    deps = compose_dependencies()
    return reflection.delete_reflection(event, None, repository=deps["reflection_repository"], s3=deps["s3"])


def demo_trace(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    def action() -> dict[str, Any]:
        deps, learner_id = compose_dependencies(), _learner_id(event)
        table = getattr(deps["trace_repository"], "table")
        items = table.query(KeyConditionExpression="learnerId = :learnerId", ExpressionAttributeValues={":learnerId": learner_id}).get("Items", [])
        entries = [{"eventTimestamp": item.get("scoredAt", item.get("timestamp", "")), "provenance": item.get("provenance", "seeded").title(), "verificationRetries": item.get("retryCount", item.get("retries", 0)), "masterySnapshot": item.get("masterySnapshot")} for item in items]
        return _response(200, {"entries": entries})
    return _adapt(action)


__all__ = ["init_learner", "baseline_next", "baseline_submit", "next_question", "run_and_check", "generate", "next_hint", "create_reflection", "delete_reflection", "demo_trace"]


def get_reflection(event, context):
    deps = compose_dependencies()
    return _adapt(lambda: reflection.get_reflection(event, context, repository=deps["reflection_repository"], s3=deps["s3"]))


def practice_history(event, context):
    deps, learner_id, topic = compose_dependencies(), _learner_id(event), _topic(event)
    table = deps["attempt_repository"].table
    attempts = table.query(KeyConditionExpression="learnerId = :learnerId", ExpressionAttributeValues={":learnerId": learner_id}).get("Items", [])
    entries = []
    for attempt in attempts:
        question = deps["question_repository"].get(attempt["questionId"])
        if question is not None and question.topic is topic:
            entries.append({"question": _public_question(question), "passed": attempt["passed"]})
    return _response(200, {"entries": entries})


def _guard(handler):
    from functools import wraps
    @wraps(handler)
    def guarded(event, context):
        return _adapt(lambda: handler(event, context))
    return guarded


__all__.extend(["get_reflection", "practice_history"])
for _handler_name in __all__:
    globals()[_handler_name] = _guard(globals()[_handler_name])
