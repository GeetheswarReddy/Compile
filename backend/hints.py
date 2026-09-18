"""The four-step, explicitly requested hint ladder."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .contracts import HintLevel, MasteryState


def _response(status_code: int, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"statusCode": status_code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(dict(payload or {}))}


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("body", {})
    if isinstance(raw, Mapping):
        return dict(raw)
    value = json.loads(raw or "{}")
    if not isinstance(value, dict):
        raise ValueError("body must be a JSON object")
    return value


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


def _learner_id(event: Mapping[str, Any]) -> str:
    for key, value in (event.get("headers") or {}).items():
        if key.lower() == "x-learner-id" and isinstance(value, str) and value.strip():
            return value
    value = event.get("learnerId")
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError("X-Learner-Id is required")


def _hint_text(question: Any, level: HintLevel) -> str:
    hints = getattr(question, "hints", None)
    if isinstance(hints, (tuple, list)) and len(hints) >= int(level):
        return str(hints[int(level) - 1])
    if level is HintLevel.NUDGE:
        return "Nudge: identify the input-to-output relationship and test a small example."
    if level is HintLevel.APPROACH:
        return "Approach: choose the data structure or traversal that preserves the needed information."
    if level is HintLevel.PSEUDOCODE:
        return "Pseudocode: initialize the needed state, process each input once, then return the requested result."
    return question.reference_solution


def get_next_hint(event: Mapping[str, Any], context: Any) -> dict[str, Any]:
    """Return exactly the next requested level and reduce topic confidence."""
    try:
        body = _body(event)
        learner_id = _learner_id(event)
        question_id = body.get("questionId") or event.get("questionId")
        current_level = body.get("currentLevel", event.get("currentLevel", 0))
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("questionId is required")
        if isinstance(current_level, bool) or not isinstance(current_level, int) or not 0 <= current_level <= 4:
            raise ValueError("currentLevel must be an integer between 0 and 4")
        question_repo = _dependency(context, "question_repository", "questions")
        mastery_repo = _dependency(context, "mastery_repository", "mastery")
        question = question_repo.get(question_id)
        if question is None:
            return _response(404, {"error": "question not found"})
        if current_level >= int(HintLevel.REFERENCE_SOLUTION):
            return _response(409, {"error": "all hint levels have been requested", "level": current_level})

        level = HintLevel(current_level + 1)
        mastery = mastery_repo.get(learner_id, question.topic)
        if mastery is None:
            mastery = MasteryState(learner_id, question.topic, question.difficulty)
        lowered = mastery_repo.save(MasteryState(
            learner_id, question.topic, mastery.score, max(0.0, mastery.confidence - 0.1),
        ))
        return _response(200, {"level": int(level), "name": level.name, "hint": _hint_text(question, level), "mastery": {
            "topic": lowered.topic.value, "score": lowered.score, "confidence": lowered.confidence,
        }})
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc)})


__all__ = ["get_next_hint"]
