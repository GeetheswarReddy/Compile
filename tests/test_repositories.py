from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

from boto3.dynamodb.types import TypeSerializer, TypeDeserializer

from backend.contracts import (
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
from backend.repositories import (
    AttemptRepository,
    LearnerRepository,
    MasteryRepository,
    PreparedQuestionRepository,
    QuestionRepository,
    ReflectionRepository,
    TraceRepository,
)
from backend.table_names import KEY_SCHEMAS


class DynamoNumberTable:
    """Exercise boto3's actual storage conversion without making AWS calls."""

    def __init__(self):
        self.item = None

    def put_item(self, *, Item, **kwargs):
        self.item = TypeSerializer().serialize(Item)
        return {}

    def get_item(self, *, Key, **kwargs):
        return {} if self.item is None else {"Item": TypeDeserializer().deserialize(self.item)}


def test_mastery_uses_real_dynamo_number_round_trip():
    table = DynamoNumberTable()
    repo = MasteryRepository(table)
    mastery = MasteryState("learner", Topic.ARRAYS, 5, 0.9)
    repo.save(mastery)
    assert table.get_item(Key={})["Item"]["confidence"] == Decimal("0.9")
    loaded = repo.get("learner", Topic.ARRAYS)
    assert loaded == mastery
    assert type(loaded.score) is int
    assert type(loaded.confidence) is float


def test_learner_uses_real_dynamo_number_round_trip():
    repo = LearnerRepository(DynamoNumberTable())
    learner = LearnerState("learner", False, 2, 1)
    repo.save(learner)
    assert repo.get("learner") == learner


def test_every_deployed_seed_loads_after_dynamo_serialization():
    from scripts.seed_questions import _dynamo_item
    from backend.repositories import _question_from_item
    corpus = json.loads((Path(__file__).resolve().parents[1] / "seed/questions.json").read_text())
    for seed in corpus["questions"]:
        table = DynamoNumberTable()
        table.put_item(Item=_dynamo_item(seed, corpus["version"]))
        question = _question_from_item(table.get_item(Key={})["Item"])
        assert question.question_id == seed["question_id"]
        assert type(question.difficulty) is int
        # Nested numbers must also work in JSON payloads and code execution.
        json.dumps([{ "input": case.input_data, "expected": case.expected_output }
                    for case in question.hidden_tests])


class FakeTable:
    def __init__(self):
        self.items = {}
        self.calls = []

    def put_item(self, **kwargs):
        self.calls.append(("put_item", kwargs))
        item = kwargs["Item"]
        if kwargs.get("ConditionExpression") and any(
            existing.get("learnerId") == item.get("learnerId")
            and existing.get("questionId") == item.get("questionId")
            for existing in self.items.values()
        ):
            raise ConditionalCheckFailedException()
        self.items[tuple(item.get(key) for key in ("learnerId", "questionId", "learnerTopic"))] = item

    def get_item(self, *, Key, **kwargs):
        return {"Item": self.items.get(tuple(Key.get(key) for key in ("learnerId", "questionId", "learnerTopic")))}

    def query(self, **kwargs):
        value = kwargs["ExpressionAttributeValues"][":learnerTopic"]
        return {"Items": [item for item in self.items.values() if item.get("learnerTopic") == value]}

    def update_item(self, *, Key, **kwargs):
        item = next((item for item in self.items.values() if all(item.get(k) == v for k, v in Key.items())), None)
        if item is None:
            item = dict(Key)
            self.items[tuple(item.get(key) for key in ("learnerId", "questionId", "learnerTopic"))] = item
        item["generationFailureCount"] = item.get("generationFailureCount", 0) + kwargs["ExpressionAttributeValues"][":one"]
        return {"Attributes": {"generationFailureCount": item["generationFailureCount"]}}

    def delete_item(self, *, Key, **kwargs):
        found = next((item for item in self.items.values() if all(item.get(k) == v for k, v in Key.items())), None)
        if found:
            self.items.pop(tuple(found.get(key) for key in ("learnerId", "questionId", "learnerTopic")))
        return {"Attributes": found} if kwargs.get("ReturnValues") == "ALL_OLD" and found else {}


class ConditionalCheckFailedException(Exception):
    pass


def question():
    return Question("q1", Topic.ARRAYS, 3, "Prompt", "", (TestCase(1, 1), TestCase(2, 2)), "return 1", Provenance.GENERATED)


def test_declared_key_shapes_are_exact():
    assert KEY_SCHEMAS["learners"] == ("learnerId",)
    assert KEY_SCHEMAS["mastery"] == ("learnerId", "topic")
    assert KEY_SCHEMAS["attempts"] == ("learnerId", "questionId")
    assert KEY_SCHEMAS["prepared_questions"] == ("learnerTopic", "questionId")


def test_scored_attempt_is_conditional():
    table = FakeTable()
    repo = AttemptRepository(table)
    verdict = SubmissionVerdict(True)
    assert repo.put_scored_attempt("learner", "q1", verdict)
    assert not repo.put_scored_attempt("learner", "q1", verdict)


def test_consumed_prepared_question_is_not_returned():
    table = FakeTable()
    repo = PreparedQuestionRepository(table)
    prepared = PreparedQuestion("learner", Topic.ARRAYS, question(), datetime.now(timezone.utc) + timedelta(minutes=1))
    repo.save(prepared)
    assert repo.get("learner", Topic.ARRAYS) == prepared
    assert repo.consume("learner", Topic.ARRAYS) == prepared
    assert repo.get("learner", Topic.ARRAYS) is None


def test_learner_mastery_and_question_round_trip_with_declared_keys():
    learner_table = FakeTable()
    learner_repo = LearnerRepository(learner_table)
    learner = LearnerState("learner", True, 2, 1)
    assert learner_repo.save(learner) == learner
    assert learner_repo.get("learner") == learner
    assert learner_table.calls[-1][1]["Item"].keys() >= {"learnerId"}

    mastery_table = FakeTable()
    mastery_repo = MasteryRepository(mastery_table)
    mastery = MasteryState("learner", Topic.STRINGS, 6, 0.75)
    assert mastery_repo.save(mastery) == mastery
    assert mastery_repo.get("learner", Topic.STRINGS) == mastery


def test_mastery_generation_failure_count_is_persisted_and_incremented():
    table = FakeTable()
    repo = MasteryRepository(table)
    mastery = MasteryState("learner", Topic.ARRAYS, 3)
    repo.save(mastery)
    assert repo.increment_generation_failure("learner", Topic.ARRAYS) == 1
    assert repo.increment_generation_failure("learner", Topic.ARRAYS) == 2
    assert table.items[("learner", None, None)]["generationFailureCount"] == 2
    repo.save(MasteryState("learner", Topic.ARRAYS, 4))
    assert repo.increment_generation_failure("learner", Topic.ARRAYS) == 3

    question_table = FakeTable()
    question_repo = QuestionRepository(question_table)
    assert question_repo.save(question()) == question()
    assert question_repo.get("q1") == question()


def test_attempt_round_trip_preserves_bounded_failed_cases_and_metadata():
    table = FakeTable()
    repo = AttemptRepository(table)
    verdict = SubmissionVerdict(False, (FailedCase([1], 2, 3),))
    assert repo.put_scored_attempt("learner", "q1", verdict, scoredAt="now")
    assert repo.get("learner", "q1") == {
        "learnerId": "learner",
        "questionId": "q1",
        "passed": False,
        "failedCases": [{"input_data": [1], "expected_output": 2, "actual_output": 3}],
        "scoredAt": "now",
    }


def test_trace_and_reflection_use_composite_keys():
    trace_table = FakeTable()
    trace_repo = TraceRepository(trace_table)
    trace_id = trace_repo.append("learner", {"provenance": Provenance.GENERATED})
    assert trace_repo.get("learner", trace_id) == {
        "learnerId": "learner",
        "traceId": trace_id,
        "provenance": "generated",
    }
    assert trace_table.calls[-1][1]["Item"]["learnerId"] == "learner"

    reflection_table = FakeTable()
    reflection_repo = ReflectionRepository(reflection_table)
    saved = reflection_repo.save("learner", "q1", {"s3Key": "recording"})
    assert reflection_repo.get("learner", "q1") == saved
    reflection_repo.delete("learner", "q1")
    assert reflection_repo.get("learner", "q1") is None


def test_expired_prepared_question_is_deleted_and_not_returned():
    table = FakeTable()
    repo = PreparedQuestionRepository(table)
    expired = PreparedQuestion("learner", Topic.ARRAYS, question(), datetime.now(timezone.utc))
    repo.save(expired)
    assert repo.get("learner", Topic.ARRAYS) is None
    assert repo.consume("learner", Topic.ARRAYS) is None
