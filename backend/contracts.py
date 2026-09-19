"""Immutable domain contracts and safe public payload serializers for Compile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Mapping


MIN_SCORE = 1
MAX_SCORE = 10
MAX_VERDICT_FAILURES = 2


class Topic(str, Enum):
    """The only practice topics supported by the demo."""

    ARRAYS = "Arrays"
    STRINGS = "Strings"
    HASH_MAPS_TWO_POINTERS = "Hash Maps/Two Pointers"


class Provenance(str, Enum):
    """How a question entered the available question pool."""

    SEEDED = "seeded"
    CURATED = "curated"
    GENERATED = "generated"


class HintLevel(IntEnum):
    """The four learner-requested hint levels, in disclosure order."""

    NUDGE = 1
    APPROACH = 2
    PSEUDOCODE = 3
    REFERENCE_SOLUTION = 4


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_score(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_SCORE <= value <= MAX_SCORE:
        raise ValueError(f"{field_name} must be an integer between {MIN_SCORE} and {MAX_SCORE}")


@dataclass(frozen=True, slots=True)
class TestCase:
    """A private execution test retained only inside backend domain objects."""

    __test__ = False

    input_data: Any
    expected_output: Any
    positional: bool = False


@dataclass(frozen=True, slots=True)
class FailedCase:
    """A failed case that is safe to include in a submission verdict."""

    input_data: Any
    expected_output: Any
    actual_output: Any


@dataclass(frozen=True, slots=True)
class Question:
    """A verified Python exercise, including backend-only execution material."""

    question_id: str
    topic: Topic
    difficulty: int
    prompt: str
    starter_code: str
    hidden_tests: tuple[TestCase, ...]
    reference_solution: str
    provenance: Provenance
    technique_tag: str = ""
    examples: tuple[TestCase, ...] = ()
    verification_retries: int = 0

    def __post_init__(self) -> None:
        _require_non_empty(self.question_id, "question_id")
        if not isinstance(self.topic, Topic):
            raise ValueError("topic must be a Topic")
        _require_score(self.difficulty, "difficulty")
        _require_non_empty(self.prompt, "prompt")
        if not isinstance(self.starter_code, str):
            raise ValueError("starter_code must be a string")
        if not isinstance(self.hidden_tests, tuple) or not 2 <= len(self.hidden_tests) <= 3:
            raise ValueError("hidden_tests must contain two or three test cases")
        if not all(isinstance(test_case, TestCase) for test_case in self.hidden_tests):
            raise ValueError("hidden_tests must contain TestCase values")
        _require_non_empty(self.reference_solution, "reference_solution")
        if not isinstance(self.provenance, Provenance):
            raise ValueError("provenance must be a Provenance")


@dataclass(frozen=True, slots=True)
class SubmissionVerdict:
    """The bounded feedback returned after a Run & Check submission."""

    passed: bool
    failed_cases: tuple[FailedCase, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be a bool")
        if not isinstance(self.failed_cases, tuple):
            raise ValueError("failed_cases must be a tuple")
        if len(self.failed_cases) > MAX_VERDICT_FAILURES:
            raise ValueError("a verdict may expose at most two failed cases")
        if not all(isinstance(case, FailedCase) for case in self.failed_cases):
            raise ValueError("failed_cases must contain FailedCase values")
        if self.passed and self.failed_cases:
            raise ValueError("a passing verdict cannot include failed cases")


@dataclass(frozen=True, slots=True)
class MasteryState:
    """A learner's score and confidence for one topic."""

    learner_id: str
    topic: Topic
    score: int
    confidence: float = 1.0

    def __post_init__(self) -> None:
        _require_non_empty(self.learner_id, "learner_id")
        if not isinstance(self.topic, Topic):
            raise ValueError("topic must be a Topic")
        _require_score(self.score, "score")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence must be a number between 0 and 1")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be a number between 0 and 1")


@dataclass(frozen=True, slots=True)
class LearnerState:
    """Anonymous learner progress and per-learner action counts."""

    learner_id: str
    baseline_completed: bool = False
    run_check_actions: int = 0
    generation_requests: int = 0

    def __post_init__(self) -> None:
        _require_non_empty(self.learner_id, "learner_id")
        if not isinstance(self.baseline_completed, bool):
            raise ValueError("baseline_completed must be a bool")
        for value, field_name, maximum in (
            (self.run_check_actions, "run_check_actions", 5),
            (self.generation_requests, "generation_requests", 2),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
                raise ValueError(f"{field_name} must be an integer between 0 and {maximum}")


@dataclass(frozen=True, slots=True)
class PreparedQuestion:
    """A generated question reserved for a learner and topic until expiry."""

    learner_id: str
    topic: Topic
    question: Question
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.learner_id, "learner_id")
        if not isinstance(self.topic, Topic):
            raise ValueError("topic must be a Topic")
        if not isinstance(self.question, Question):
            raise ValueError("question must be a Question")
        if self.question.topic is not self.topic:
            raise ValueError("prepared question topic must match topic")
        if not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be a timezone-aware datetime")


def serialize_question(question: Question) -> dict[str, Any]:
    """Return the allow-listed question payload; never expose execution secrets."""

    return {
        "questionId": question.question_id,
        "topic": question.topic.value,
        "difficulty": question.difficulty,
        "prompt": question.prompt,
        "starterCode": question.starter_code,
        "provenance": question.provenance.value,
        "techniqueTag": question.technique_tag,
        "examples": [{"input": case.input_data, "expected": case.expected_output} for case in question.examples],
    }


def serialize_verdict(verdict: SubmissionVerdict) -> dict[str, Any]:
    """Return pass/fail and at most two learner-visible failures."""

    return {
        "passed": verdict.passed,
        "failedCases": [
            {
                "input": failed_case.input_data,
                "expected": failed_case.expected_output,
                "actual": failed_case.actual_output,
            }
            for failed_case in verdict.failed_cases
        ],
    }


def serialize_mastery_state(mastery: MasteryState) -> dict[str, Any]:
    return {
        "topic": mastery.topic.value,
        "score": mastery.score,
        "confidence": mastery.confidence,
    }


def serialize_learner_state(learner: LearnerState) -> dict[str, Any]:
    return {
        "learnerId": learner.learner_id,
        "baselineCompleted": learner.baseline_completed,
        "runCheckActions": learner.run_check_actions,
        "generationRequests": learner.generation_requests,
    }


def serialize_prepared_question(prepared: PreparedQuestion) -> dict[str, Any]:
    return {
        "topic": prepared.topic.value,
        "question": serialize_question(prepared.question),
        "expiresAt": prepared.expires_at.isoformat(),
    }


def serialize_hint_level(level: HintLevel) -> dict[str, Any]:
    if not isinstance(level, HintLevel):
        raise ValueError("level must be a HintLevel")
    return {"level": int(level), "name": level.name}


def serialize_public_payload(value: Any) -> Mapping[str, Any]:
    """Serialize any public contract explicitly supported by this module."""

    if isinstance(value, Question):
        return serialize_question(value)
    if isinstance(value, SubmissionVerdict):
        return serialize_verdict(value)
    if isinstance(value, MasteryState):
        return serialize_mastery_state(value)
    if isinstance(value, LearnerState):
        return serialize_learner_state(value)
    if isinstance(value, PreparedQuestion):
        return serialize_prepared_question(value)
    if isinstance(value, HintLevel):
        return serialize_hint_level(value)
    raise TypeError(f"unsupported public payload type: {type(value).__name__}")
