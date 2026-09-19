"""The fixed five-question baseline assessment and resume point."""

from __future__ import annotations

from typing import Any

from .contracts import LearnerState, MasteryState, Question, SubmissionVerdict, Topic
from .learner_state import init_learner

BASELINE_TARGETS: tuple[tuple[Topic, int], ...] = (
    (Topic.ARRAYS, 3), (Topic.ARRAYS, 6),
    (Topic.STRINGS, 3), (Topic.STRINGS, 6),
    (Topic.HASH_MAPS_TWO_POINTERS, 5),
)


def _questions(repo: Any) -> list[Question]:
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


def _baseline_question(question_repo: Any, topic: Topic, difficulty: int, questions=None) -> Question:
    candidates = [q for q in (questions if questions is not None else _questions(question_repo)) if q.topic is topic and q.difficulty == difficulty and q.provenance.value == "seeded"]
    if not candidates:
        raise LookupError(f"no baseline question for {topic.value} at difficulty {difficulty}")
    return sorted(candidates, key=lambda q: q.question_id)[0]


def baseline_questions(question_repo):
    questions = _questions(question_repo)
    return [_baseline_question(question_repo, topic, difficulty, questions) for topic, difficulty in BASELINE_TARGETS]


def _answered(attempt_repo: Any, learner_id: str, question_id: str) -> bool:
    return attempt_repo.get(learner_id, question_id) is not None


def get_baseline_next(learner_id: str, learner_repo: Any, question_repo: Any, attempt_repo: Any) -> Question | None:
    learner = init_learner(learner_repo, learner_id)
    if learner.baseline_completed:
        return None
    for question in baseline_questions(question_repo):
        if not _answered(attempt_repo, learner_id, question.question_id):
            return question
    return None


def submit_baseline(
    learner_id: str, question_id: str, result: bool | SubmissionVerdict,
    learner_repo: Any, question_repo: Any, attempt_repo: Any, mastery_repo: Any,
) -> LearnerState:
    """Record one baseline answer and advance completion when all five are done.

    ``result`` is the caller-provided verdict; this boundary deliberately does
    not execute learner code. A topic's initial mastery is the baseline score,
    adjusted by correctness and clamped by the shared contract range.
    """
    learner = init_learner(learner_repo, learner_id)
    if learner.baseline_completed:
        return learner

    question = question_repo.get(question_id)
    fixed_questions = baseline_questions(question_repo)
    if question is None or question_id not in {q.question_id for q in fixed_questions}:
        raise ValueError("question_id is not a baseline question")
    passed = result.passed if isinstance(result, SubmissionVerdict) else result
    if not isinstance(passed, bool):
        raise ValueError("result must be a bool or SubmissionVerdict")
    if not attempt_repo.put_scored_attempt(learner_id, question_id, result if isinstance(result, SubmissionVerdict) else SubmissionVerdict(passed), baseline=True):
        return init_learner(learner_repo, learner_id)
    score = max(1, min(10, question.difficulty + (1 if passed else -1)))
    mastery_repo.save(MasteryState(learner_id, question.topic, score))
    completed = all(
        _answered(attempt_repo, learner_id, q.question_id) for q in fixed_questions
    )
    learner = init_learner(learner_repo, learner_id)
    updated = LearnerState(learner_id, completed, learner.run_check_actions, learner.generation_requests)
    return learner_repo.save(updated)


__all__ = ["BASELINE_TARGETS", "get_baseline_next", "submit_baseline"]
