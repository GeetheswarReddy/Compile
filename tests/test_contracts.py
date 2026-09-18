from datetime import datetime, timezone

import pytest

from backend.contracts import (
    FailedCase,
    HintLevel,
    LearnerState,
    MasteryState,
    PreparedQuestion,
    Provenance,
    Question,
    SubmissionVerdict,
    TestCase,
    Topic,
    serialize_public_payload,
)


def _question() -> Question:
    return Question(
        question_id="arrays-1",
        topic=Topic.ARRAYS,
        difficulty=3,
        prompt="Return the first item.",
        starter_code="def first(items):\n    pass\n",
        hidden_tests=(TestCase([1], 1), TestCase([2], 2)),
        reference_solution="def first(items):\n    return items[0]\n",
        provenance=Provenance.SEEDED,
    )


@pytest.mark.parametrize("score", [0, 11, 1.5, True])
def test_question_rejects_invalid_difficulty(score: object) -> None:
    with pytest.raises(ValueError):
        Question(
            question_id="q1",
            topic=Topic.ARRAYS,
            difficulty=score,  # type: ignore[arg-type]
            prompt="Prompt",
            starter_code="",
            hidden_tests=(TestCase(1, 1), TestCase(2, 2)),
            reference_solution="return 1",
            provenance=Provenance.SEEDED,
        )


def test_contracts_reject_invalid_topics() -> None:
    with pytest.raises(ValueError):
        Topic("Linked Lists")
    with pytest.raises(ValueError):
        MasteryState("learner-1", "Arrays", 3)  # type: ignore[arg-type]


def test_verdict_never_exposes_more_than_two_failures() -> None:
    failures = tuple(FailedCase(index, index, index + 1) for index in range(3))
    with pytest.raises(ValueError, match="at most two"):
        SubmissionVerdict(False, failures)


def test_public_payloads_allow_list_safe_fields() -> None:
    question = _question()
    verdict = SubmissionVerdict(False, (FailedCase([1], 1, 0),))
    prepared = PreparedQuestion(
        learner_id="learner-1",
        topic=Topic.ARRAYS,
        question=question,
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    payloads = [
        serialize_public_payload(question),
        serialize_public_payload(verdict),
        serialize_public_payload(MasteryState("learner-1", Topic.ARRAYS, 3)),
        serialize_public_payload(LearnerState("learner-1")),
        serialize_public_payload(prepared),
        serialize_public_payload(HintLevel.APPROACH),
    ]
    rendered = repr(payloads)

    assert "hidden_tests" not in rendered
    assert "reference_solution" not in rendered
    assert "return items[0]" not in rendered
    assert payloads[0]["questionId"] == "arrays-1"
    assert payloads[1]["failedCases"] == [{"input": [1], "expected": 1, "actual": 0}]
