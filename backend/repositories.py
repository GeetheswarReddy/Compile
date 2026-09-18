"""Small DynamoDB repository adapters for Compile's domain contracts.

Repositories accept a boto3 Table-like object.  Keeping that dependency at the
edge makes the module usable in Lambda and straightforward to test with a fake
table, without requiring AWS credentials during import.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from .contracts import (
    FailedCase,
    LearnerState,
    MasteryState,
    PreparedQuestion,
    Provenance,
    Question,
    SubmissionVerdict,
    TestCase,
    Topic,
)


def _value(value: Any) -> Any:
    if isinstance(value, (Topic, Provenance)):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    if isinstance(value, list):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    return value


def _question_item(question: Question) -> dict[str, Any]:
    return {
        "questionId": question.question_id,
        "topic": question.topic.value,
        "difficulty": question.difficulty,
        "prompt": question.prompt,
        "starterCode": question.starter_code,
        "hiddenTests": [_value(asdict(test)) for test in question.hidden_tests],
        "referenceSolution": question.reference_solution,
        "provenance": question.provenance.value,
    }


def _question_from_item(item: Mapping[str, Any]) -> Question:
    tests = tuple(TestCase(t["input_data"], t["expected_output"]) for t in item["hiddenTests"])
    return Question(
        question_id=item["questionId"], topic=Topic(item["topic"]), difficulty=int(item["difficulty"]),
        prompt=item["prompt"], starter_code=item.get("starterCode", ""), hidden_tests=tests,
        reference_solution=item["referenceSolution"], provenance=Provenance(item["provenance"]),
    )


def _conditional_failure(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error", {})
        if error.get("Code") == "ConditionalCheckFailedException":
            return True
    return exc.__class__.__name__ == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in str(exc)


class _Repository:
    def __init__(self, table: Any):
        self.table = table

    def _get(self, key: dict[str, Any]) -> dict[str, Any] | None:
        return self.table.get_item(Key=key).get("Item")


class LearnerRepository(_Repository):
    def get(self, learner_id: str) -> LearnerState | None:
        item = self._get({"learnerId": learner_id})
        return None if item is None else LearnerState(
            learner_id=item["learnerId"], baseline_completed=item.get("baselineCompleted", False),
            run_check_actions=item.get("runCheckActions", 0), generation_requests=item.get("generationRequests", 0),
        )

    def save(self, learner: LearnerState) -> LearnerState:
        self.table.put_item(Item={"learnerId": learner.learner_id, "baselineCompleted": learner.baseline_completed,
                                  "runCheckActions": learner.run_check_actions, "generationRequests": learner.generation_requests})
        return learner


class MasteryRepository(_Repository):
    def get(self, learner_id: str, topic: Topic) -> MasteryState | None:
        item = self._get({"learnerId": learner_id, "topic": topic.value})
        return None if item is None else MasteryState(item["learnerId"], Topic(item["topic"]), item["score"], item.get("confidence", 1.0))

    def save(self, mastery: MasteryState) -> MasteryState:
        existing = self._get({"learnerId": mastery.learner_id, "topic": mastery.topic.value})
        self.table.put_item(Item={"learnerId": mastery.learner_id, "topic": mastery.topic.value,
                                  "score": mastery.score, "confidence": mastery.confidence,
                                  "generationFailureCount": (existing or {}).get("generationFailureCount", 0)})
        return mastery

    def increment_generation_failure(self, learner_id: str, topic: Topic) -> int:
        response = self.table.update_item(
            Key={"learnerId": learner_id, "topic": topic.value},
            UpdateExpression="SET generationFailureCount = if_not_exists(generationFailureCount, :zero) + :one",
            ExpressionAttributeValues={":zero": 0, ":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["generationFailureCount"])


class QuestionRepository(_Repository):
    def get(self, question_id: str) -> Question | None:
        item = self._get({"questionId": question_id})
        return None if item is None else _question_from_item(item)

    def save(self, question: Question) -> Question:
        self.table.put_item(Item=_question_item(question))
        return question


class AttemptRepository(_Repository):
    def get(self, learner_id: str, question_id: str) -> dict[str, Any] | None:
        return self._get({"learnerId": learner_id, "questionId": question_id})

    def put_scored_attempt(self, learner_id: str, question_id: str, verdict: SubmissionVerdict, **metadata: Any) -> bool:
        item = {**_value(metadata), "learnerId": learner_id, "questionId": question_id,
                "passed": verdict.passed, "failedCases": [_value(asdict(case)) for case in verdict.failed_cases]}
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(learnerId) AND attribute_not_exists(questionId)")
        except Exception as exc:
            if _conditional_failure(exc):
                return False
            raise
        return True

    save_scored = put_scored_attempt


class TraceRepository(_Repository):
    def get(
        self,
        key_or_learner_id: Mapping[str, Any] | str,
        trace_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Read a trace by its DynamoDB key.

        Both the repository's convenient ``(learner_id, trace_id)`` form and
        the raw ``{"learnerId": ..., "traceId": ...}`` key form are accepted.
        The latter keeps this adapter compatible with callers that already
        construct DynamoDB keys at the boundary.
        """
        if isinstance(key_or_learner_id, Mapping):
            key = dict(key_or_learner_id)
        else:
            if trace_id is None:
                raise TypeError("trace_id is required when learner_id is a string")
            key = {"learnerId": key_or_learner_id, "traceId": trace_id}
        return self._get(key)

    def append(self, learner_id: str, trace: Mapping[str, Any], trace_id: str | None = None) -> str:
        trace_id = trace_id or str(uuid4())
        self.table.put_item(Item={**_value(dict(trace)), "learnerId": learner_id, "traceId": trace_id})
        return trace_id

    put = append


class ReflectionRepository(_Repository):
    def get(self, learner_id: str, question_id: str) -> dict[str, Any] | None:
        return self._get({"learnerId": learner_id, "questionId": question_id})

    def save(self, learner_id: str, question_id: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        item = {**_value(dict(metadata)), "learnerId": learner_id, "questionId": question_id}
        self.table.put_item(Item=item)
        return item

    def delete(self, learner_id: str, question_id: str) -> None:
        self.table.delete_item(Key={"learnerId": learner_id, "questionId": question_id})


class PreparedQuestionRepository(_Repository):
    @staticmethod
    def _key(learner_id: str, topic: Topic, question_id: str | None = None) -> dict[str, str]:
        key = {"learnerTopic": f"{learner_id}#{topic.value}"}
        if question_id is not None:
            key["questionId"] = question_id
        return key

    def save(self, prepared: PreparedQuestion) -> PreparedQuestion:
        self.table.put_item(Item={"learnerTopic": f"{prepared.learner_id}#{prepared.topic.value}",
                                  "questionId": prepared.question.question_id, "topic": prepared.topic.value,
                                  "question": _question_item(prepared.question), "expiresAt": prepared.expires_at.isoformat()})
        return prepared

    def get(self, learner_id: str, topic: Topic) -> PreparedQuestion | None:
        item = self._first(learner_id, topic)
        return self._from_item(item, learner_id, topic) if item else None

    def consume(self, learner_id: str, topic: Topic) -> PreparedQuestion | None:
        item = self._first(learner_id, topic)
        if not item:
            return None
        result = self.table.delete_item(
            Key=self._key(learner_id, topic, item["questionId"]), ReturnValues="ALL_OLD"
        )
        item = result.get("Attributes")
        return self._from_item(item, learner_id, topic) if item else None

    def delete(self, learner_id: str, topic: Topic, question_id: str | None = None) -> None:
        if question_id is None:
            item = self._first(learner_id, topic)
            if not item:
                return
            question_id = item["questionId"]
        self.table.delete_item(Key=self._key(learner_id, topic, question_id))

    def _first(self, learner_id: str, topic: Topic) -> Mapping[str, Any] | None:
        response = self.table.query(
            KeyConditionExpression="learnerTopic = :learnerTopic",
            ExpressionAttributeValues={":learnerTopic": f"{learner_id}#{topic.value}"},
        )
        now = datetime.now().astimezone()
        first_live = None
        for item in response.get("Items", []):
            # A malformed item must not be treated as a live prepared
            # question; DynamoDB records written by this repository always
            # contain the expiry and question sort-key attributes.
            if "expiresAt" not in item or "questionId" not in item:
                continue
            expires_at = datetime.fromisoformat(item["expiresAt"])
            if expires_at <= now:
                self.table.delete_item(Key=self._key(learner_id, topic, item["questionId"]))
                continue
            if first_live is None:
                first_live = item
        return first_live

    @staticmethod
    def _from_item(item: Mapping[str, Any], learner_id: str, topic: Topic) -> PreparedQuestion:
        return PreparedQuestion(learner_id, topic, _question_from_item(item["question"]), datetime.fromisoformat(item["expiresAt"]))
