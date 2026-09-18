"""API Gateway adapters.  Public responses are explicitly allow-listed."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping

from . import baseline, generation_orchestrator, hints, learner_state, question_select, reflection, run_check
from .contracts import Question, Topic, serialize_learner_state, serialize_question
from .dependencies import compose_dependencies
from .execution_runner import run_submission

TOPIC_IDS = {
    "arrays": Topic.ARRAYS,
    "strings": Topic.STRINGS,
    "hash-maps-two-pointers": Topic.HASH_MAPS_TWO_POINTERS,
}
TOTAL_BASELINE_QUESTIONS = 5


def _response(status: int, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(dict(payload or {}))}


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


def _answered(deps: Mapping[str, Any], learner_id: str) -> int:
    table = getattr(deps["attempt_repository"], "table", None)
    if table is None or not hasattr(table, "query"):
        return 0
    attempts = table.query(KeyConditionExpression="learnerId = :learnerId", ExpressionAttributeValues={":learnerId": learner_id}).get("Items", [])
    questions = _questions(deps["question_repository"])
    baseline_ids = {
        question.question_id
        for topic, difficulty in baseline.BASELINE_TARGETS
        for question in questions
        if question.topic is topic and question.difficulty == difficulty
    }
    return sum(1 for attempt in attempts if attempt.get("questionId") in baseline_ids)


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
    except LookupError as exc:
        return _response(404, {"error": str(exc)})


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
        learner = baseline.submit_baseline(learner_id, question_id, run_submission(question, code), deps["learner_repository"], deps["question_repository"], deps["attempt_repository"], deps["mastery_repository"])
        next_question = baseline.get_baseline_next(learner_id, deps["learner_repository"], deps["question_repository"], deps["attempt_repository"])
        return _response(200, {"completed": learner.baseline_completed, "question": _public_question(next_question), "progress": {"answered": _answered(deps, learner_id), "total": TOTAL_BASELINE_QUESTIONS}})
    return _adapt(action)


def next_question(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    def action() -> dict[str, Any]:
        deps, learner_id, topic = compose_dependencies(), _learner_id(event), _topic(event)
        question = question_select.get_next_question(learner_id, topic, deps["mastery_repository"], deps["question_repository"], deps["attempt_repository"], deps["prepared_repository"])
        return _response(200, {"question": _public_question(question)})
    return _adapt(action)


def run_and_check(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    response = run_check.run_check(event, compose_dependencies())
    if response.get("statusCode") != 200:
        return response
    payload = json.loads(response["body"])
    # The browser contract places the bounded verdict fields at top level.
    return _response(200, {**payload.get("verdict", {}), "scored": payload.get("scored", False), "mastery": payload.get("mastery")})


def generate(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    deps = compose_dependencies()
    return generation_orchestrator.start_generation(event, None, learner_repository=deps["learner_repository"], demo_quota=deps["demo_quota"], step_functions_client=deps["step_functions_client"], state_machine_arn=os.environ.get("GENERATION_STATE_MACHINE_ARN"))


def next_hint(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    return hints.get_next_hint(event, compose_dependencies())


def create_reflection(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    del context
    deps = compose_dependencies()
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
