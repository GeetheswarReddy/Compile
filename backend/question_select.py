"""Selection of the next unattempted question for a topic."""

from __future__ import annotations

from typing import Any

from .contracts import MasteryState, PreparedQuestion, Question, Topic


def _all(repo: Any) -> list[Question]:
    if hasattr(repo, "all"):
        return list(repo.all())
    if hasattr(repo, "list"):
        return list(repo.list())
    if hasattr(repo, "questions"):
        return list(repo.questions.values() if isinstance(repo.questions, dict) else repo.questions)
    if hasattr(repo, "items") and not callable(repo.items):
        return list(repo.items.values() if isinstance(repo.items, dict) else repo.items)
    table = getattr(repo, "table", None)
    if table is not None and hasattr(table, "scan"):
        from .repositories import _question_from_item
        return [_question_from_item(item) for item in table.scan().get("Items", [])]
    raise TypeError("question repository must provide all/list or a scan-capable table")


def _attempted(repo: Any, learner_id: str, question_id: str) -> bool:
    return repo.get(learner_id, question_id) is not None


def get_next_question(
    learner_id: str, topic: Topic, mastery_repo: Any, question_repo: Any,
    attempt_repo: Any, prepared_repo: Any = None,
) -> Question | None:
    if not isinstance(learner_id, str) or not learner_id.strip():
        raise ValueError("learner_id must be a non-empty string")
    if not isinstance(topic, Topic):
        topic = Topic(topic)
    if prepared_repo is not None:
        prepared = prepared_repo.consume(learner_id, topic) if hasattr(prepared_repo, "consume") else prepared_repo.get(learner_id, topic)
        if isinstance(prepared, PreparedQuestion) and not _attempted(attempt_repo, learner_id, prepared.question.question_id):
            return prepared.question
    mastery = mastery_repo.get(learner_id, topic)
    if mastery is None:
        mastery = MasteryState(learner_id, topic, 1)
    available = [
        q for q in _all(question_repo)
        if q.topic is topic and not _attempted(attempt_repo, learner_id, q.question_id)
    ]
    if not available:
        if prepared_repo is not None:
            prepared_repo.delete(learner_id, topic)
        return None
    return min(available, key=lambda q: (abs(q.difficulty - mastery.score), q.question_id))


__all__ = ["get_next_question"]
