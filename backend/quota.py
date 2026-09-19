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
        return None
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
    if hasattr(demo, "consume"):
        return demo.consume(learner_id, kind)
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


class DynamoQuota:
    """Atomic, persistent demo and learner limits. Missing counts start at zero.

    Any storage failure denies the request. Baseline and verification use only
    the shared execution budget, leaving the learner's five practice checks.
    """
    def __init__(self, client, table_name, learners_table):
        self.client, self.table_name, self.learners_table = client, table_name, learners_table

    def consume(self, learner_id=None, kind="execution"):
        field = "execution_submissions" if kind == "execution" else "generation_attempts"
        limit = DEMO_EXECUTION_LIMIT if kind == "execution" else DEMO_GENERATION_LIMIT
        other = "generation_attempts" if kind == "execution" else "execution_submissions"
        other_limit = DEMO_GENERATION_LIMIT if kind == "execution" else DEMO_EXECUTION_LIMIT
        operations = [{"Update": {
            "TableName": self.table_name, "Key": {"quotaId": {"S": "demo"}},
            "UpdateExpression": "SET #n = if_not_exists(#n, :zero) + :one",
            "ConditionExpression": "(attribute_not_exists(#n) OR #n < :limit) AND (attribute_not_exists(#other) OR #other < :otherLimit)",
            "ExpressionAttributeNames": {"#n": field, "#other": other},
            "ExpressionAttributeValues": {":zero": {"N": "0"}, ":one": {"N": "1"}, ":limit": {"N": str(limit)}, ":otherLimit": {"N": str(other_limit)}},
        }}]
        if learner_id is not None:
            learner_field = "runCheckActions" if kind == "execution" else "generationRequests"
            learner_limit = LEARNER_EXECUTION_LIMIT if kind == "execution" else LEARNER_GENERATION_LIMIT
            other_field = "generationRequests" if kind == "execution" else "runCheckActions"
            other_learner_limit = LEARNER_GENERATION_LIMIT if kind == "execution" else LEARNER_EXECUTION_LIMIT
            operations.append({"Update": {
                "TableName": self.learners_table, "Key": {"learnerId": {"S": learner_id}},
                "UpdateExpression": "SET #n = if_not_exists(#n, :zero) + :one",
                "ConditionExpression": "baselineCompleted = :yes AND (attribute_not_exists(#n) OR #n < :limit) AND (attribute_not_exists(#other) OR #other < :otherLimit)",
                "ExpressionAttributeNames": {"#n": learner_field, "#other": other_field},
                "ExpressionAttributeValues": {":zero": {"N": "0"}, ":one": {"N": "1"}, ":limit": {"N": str(learner_limit)}, ":yes": {"BOOL": True}, ":otherLimit": {"N": str(other_learner_limit)}},
            }})
        try:
            self.client.transact_write_items(TransactItems=operations)
            return True
        except Exception:
            return False

    def exhausted(self):
        try:
            item = self.client.get_item(TableName=self.table_name, Key={"quotaId": {"S": "demo"}}, ConsistentRead=True).get("Item", {})
            return (int(item.get("execution_submissions", {"N": "0"})["N"]) >= DEMO_EXECUTION_LIMIT
                    or int(item.get("generation_attempts", {"N": "0"})["N"]) >= DEMO_GENERATION_LIMIT)
        except Exception:
            return True
