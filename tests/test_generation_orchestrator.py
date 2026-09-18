from datetime import datetime, timezone

from backend.contracts import MasteryState, Provenance, Question, TestCase, Topic
from backend.generation_handlers import handle_generated_candidate
from backend.generation_orchestrator import (
    MAX_CANDIDATES,
    generation_state_machine_definition,
    start_generation,
)


class Prepared:
    def __init__(self):
        self.items = []

    def save(self, value):
        self.items.append(value)
        return value


class Questions:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class Mastery:
    def get(self, learner_id, topic):
        return MasteryState(learner_id, topic, 4)


class MasteryWithFailures:
    def __init__(self):
        self.values = {}

    def get(self, learner_id, topic):
        return MasteryState(learner_id, topic, 4)

    def increment_generation_failure(self, learner_id, topic):
        key = (learner_id, topic)
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


class LearnerRepository:
    def __init__(self):
        self.learner = None

    def get(self, learner_id):
        return self.learner

    def save(self, learner):
        self.learner = learner
        return learner


class StepFunctions:
    def __init__(self):
        self.calls = []

    def start_execution(self, **kwargs):
        self.calls.append(kwargs)
        return {"executionArn": "execution-arn"}


def question(question_id="generated-1", provenance=Provenance.GENERATED):
    return Question(
        question_id, Topic.ARRAYS, 4, "Return the item", "", (TestCase([1], 1), TestCase([2], 2)),
        "def answer(items):\n    return items[0]\n", provenance,
    )


def candidate():
    value = question()
    return {
        "questionId": value.question_id,
        "topic": value.topic.value,
        "difficulty": value.difficulty,
        "prompt": value.prompt,
        "starterCode": value.starter_code,
        "hiddenTests": [{"input": test.input_data, "expected": test.expected_output} for test in value.hidden_tests],
        "referenceSolution": value.reference_solution,
    }


def test_verified_candidate_is_stored_as_prepared_question():
    prepared = Prepared()
    result = handle_generated_candidate(
        {"learnerId": "learner", "topic": Topic.ARRAYS.value, "candidate": candidate()},
        prepared_repository=prepared,
        verifier=lambda value: value.question_id == "generated-1",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result["status"] == "accepted"
    assert prepared.items[0].question.provenance is Provenance.GENERATED


def test_stale_candidate_is_discarded_without_persistence_or_failure():
    prepared, mastery = Prepared(), MasteryWithFailures()
    result = handle_generated_candidate(
        {"learnerId": "learner", "topic": Topic.ARRAYS.value, "candidate": candidate(), "deadline": "2025-12-31T23:59:59+00:00"},
        prepared_repository=prepared, mastery_repository=mastery, now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result == {"status": "stale", "discarded": True}
    assert prepared.items == []
    assert mastery.values == {}


def test_third_failed_candidate_increments_counter_and_uses_nearest_curated_question():
    fallback = question("seeded-4", Provenance.SEEDED)
    prepared, mastery = Prepared(), MasteryWithFailures()
    common = {
        "learnerId": "learner", "topic": Topic.ARRAYS.value, "candidate": candidate(),
        "prepared_repository": prepared,
    }
    assert handle_generated_candidate({**common, "attempt": 1}, prepared_repository=prepared, verifier=lambda _: False)["status"] == "retry"
    assert handle_generated_candidate({**common, "attempt": 2}, prepared_repository=prepared, verifier=lambda _: False)["status"] == "retry"
    result = handle_generated_candidate(
        {**common, "attempt": MAX_CANDIDATES}, prepared_repository=prepared,
        question_repository=Questions([fallback]), mastery_repository=mastery,
        verifier=lambda _: False,
    )
    assert result["status"] == "fallback"
    assert result["questionId"] == "seeded-4"
    assert mastery.values[("learner", Topic.ARRAYS)] == 1


def test_state_machine_has_three_candidates_and_budgets():
    definition = generation_state_machine_definition()
    assert definition["TimeoutSeconds"] == 8
    assert definition["States"]["GenerateCandidate"]["TimeoutSeconds"] == 2
    assert definition["States"]["GenerateCandidate"]["Retry"][0]["MaxAttempts"] == 2


def test_start_generation_consumes_quota_and_starts_execution():
    learners, step_functions = LearnerRepository(), StepFunctions()
    result = start_generation(
        {"headers": {"X-Learner-Id": "learner"}, "body": {"topic": Topic.ARRAYS.value}},
        None,
        learner_repository=learners,
        demo_quota={"generation_attempts": 0},
        step_functions_client=step_functions,
        state_machine_arn="state-machine-arn",
    )
    assert result["statusCode"] == 202
    assert learners.learner.generation_requests == 1
    assert step_functions.calls[0]["stateMachineArn"] == "state-machine-arn"
    assert '"topic": "Arrays"' in step_functions.calls[0]["input"]
