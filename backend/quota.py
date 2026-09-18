"""Fail-closed learner and demo quota consumption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

from .contracts import LearnerState

LEARNER_EXECUTION_LIMIT = 5
LEARNER_GENERATION_LIMIT = 2
DEMO_EXECUTION_LIMIT = 40
DEMO_GENERATION_LIMIT = 20


@dataclass(frozen=True, slots=True)
class QuotaState:
    execution_submissions: int = 0
    generation_attempts: int = 0


def _demo_count(store: Any, field: str) -> int | None:
    if store is None:
        return 0
    try:
        value = store.get(field) if isinstance(store, MutableMapping) else getattr(store, field)
    except (KeyError, AttributeError, TypeError):
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _set_demo_count(store: Any, field: str, value: int) -> None:
    if isinstance(store, MutableMapping):
        store[field] = value
    elif store is not None:
        setattr(store, field, value)


def _consume(learner_repository: Any, learner_id: str, kind: str, demo: Any = None) -> bool:
    learner = learner_repository.get(learner_id)
    if learner is None:
        learner = LearnerState(learner_id)
    if kind == "execution":
        learner_value, learner_limit = learner.run_check_actions, LEARNER_EXECUTION_LIMIT
        field, demo_field, demo_limit = "run_check_actions", "execution_submissions", DEMO_EXECUTION_LIMIT
    else:
        learner_value, learner_limit = learner.generation_requests, LEARNER_GENERATION_LIMIT
        field, demo_field, demo_limit = "generation_requests", "generation_attempts", DEMO_GENERATION_LIMIT
    demo_value = _demo_count(demo, demo_field)
    if learner_value >= learner_limit or demo_value is None or demo_value >= demo_limit:
        return False
    next_learner = LearnerState(
        learner.learner_id,
        learner.baseline_completed,
        learner.run_check_actions + (1 if kind == "execution" else 0),
        learner.generation_requests + (1 if kind == "generation" else 0),
    )
    learner_repository.save(next_learner)
    _set_demo_count(demo, demo_field, demo_value + 1)
    return True


def consume_execution_quota(learner_repository: Any, learner_id: str, demo_quota: Any = None) -> bool:
    return _consume(learner_repository, learner_id, "execution", demo_quota)


def consume_generation_quota(learner_repository: Any, learner_id: str, demo_quota: Any = None) -> bool:
    return _consume(learner_repository, learner_id, "generation", demo_quota)


__all__ = [
    "QuotaState", "LEARNER_EXECUTION_LIMIT", "LEARNER_GENERATION_LIMIT",
    "DEMO_EXECUTION_LIMIT", "DEMO_GENERATION_LIMIT", "consume_execution_quota",
    "consume_generation_quota",
]
