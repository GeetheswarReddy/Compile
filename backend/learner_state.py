"""Learner initialization and the small state transitions used by the API."""

from __future__ import annotations

from typing import Any

from .contracts import LearnerState


def _args(first: Any, second: Any) -> tuple[Any, str]:
    """Accept the repository-first and learner-id-first calling conventions."""
    if isinstance(first, str):
        return second, first
    return first, second


def init_learner(learner_repository: Any, learner_id: str | Any = None) -> LearnerState:
    """Return existing state or create the zeroed state for ``learner_id``.

    The argument order is intentionally tolerant of ``(repo, learner_id)`` and
    ``(learner_id, repo)`` because Lambda adapters commonly put the header first.
    Existing state is never reset by a repeated initialization request.
    """
    repository, learner_id = _args(learner_repository, learner_id)
    if not isinstance(learner_id, str) or not learner_id.strip():
        raise ValueError("learner_id must be a non-empty string")
    current = repository.get(learner_id)
    if current is not None:
        return current
    return repository.save(LearnerState(learner_id))


def update_learner(repository: Any, learner: LearnerState) -> LearnerState:
    """Persist a validated learner state for sibling boundary modules."""
    return repository.save(learner)


__all__ = ["init_learner", "update_learner"]
