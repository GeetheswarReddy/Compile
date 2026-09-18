from backend.baseline import BASELINE_TARGETS, get_baseline_next, submit_baseline
from backend.contracts import LearnerState, MasteryState, Provenance, Question, TestCase as DomainTestCase, Topic
from backend.learner_state import init_learner
from backend.question_select import get_next_question
from backend.quota import consume_execution_quota, consume_generation_quota


class Learners:
    def __init__(self):
        self.values = {}

    def get(self, learner_id):
        return self.values.get(learner_id)

    def save(self, learner):
        self.values[learner.learner_id] = learner
        return learner


class Questions:
    def __init__(self, values):
        self.values = {question.question_id: question for question in values}

    def get(self, question_id):
        return self.values.get(question_id)

    def all(self):
        return list(self.values.values())


class Attempts:
    def __init__(self):
        self.values = {}

    def get(self, learner_id, question_id):
        return self.values.get((learner_id, question_id))

    def put_scored_attempt(self, learner_id, question_id, verdict, **metadata):
        key = (learner_id, question_id)
        if key in self.values:
            return False
        self.values[key] = {"verdict": verdict, **metadata}
        return True


class Mastery:
    def __init__(self):
        self.values = {}

    def get(self, learner_id, topic):
        return self.values.get((learner_id, topic))

    def save(self, state):
        self.values[(state.learner_id, state.topic)] = state
        return state


def make_question(question_id, topic, difficulty):
    return Question(
        question_id, topic, difficulty, f"Prompt {question_id}", "",
        (DomainTestCase(1, 1), DomainTestCase(2, 2)),
        "def solve(value): return value", Provenance.SEEDED,
    )


def baseline_questions():
    return Questions([
        make_question(f"q-{index}", topic, difficulty)
        for index, (topic, difficulty) in enumerate(BASELINE_TARGETS)
    ])


def test_init_is_idempotent_and_baseline_resumes_first_unanswered():
    learners, questions, attempts, mastery = Learners(), baseline_questions(), Attempts(), Mastery()
    first = init_learner(learners, "learner-1")
    assert first == LearnerState("learner-1")
    assert get_baseline_next("learner-1", learners, questions, attempts).question_id == "q-0"

    submit_baseline("learner-1", "q-0", True, learners, questions, attempts, mastery)
    assert get_baseline_next("learner-1", learners, questions, attempts).question_id == "q-1"
    assert init_learner("learner-1", learners) == first


def test_baseline_completes_once_and_becomes_read_only():
    learners, questions, attempts, mastery = Learners(), baseline_questions(), Attempts(), Mastery()
    for index, _ in enumerate(BASELINE_TARGETS):
        state = submit_baseline("learner-1", f"q-{index}", True, learners, questions, attempts, mastery)
    assert state.baseline_completed is True
    assert get_baseline_next("learner-1", learners, questions, attempts) is None
    assert submit_baseline("learner-1", "q-0", False, learners, questions, attempts, mastery) == state
    assert attempts.values[("learner-1", "q-0")]["verdict"].passed is True


def test_selection_hits_exact_mastery_then_nearest_unattempted():
    learner_id, topic = "learner-1", Topic.ARRAYS
    questions = Questions([
        make_question("exact", topic, 5),
        make_question("near-low", topic, 4),
        make_question("near-high", topic, 6),
    ])
    attempts, mastery = Attempts(), Mastery()
    mastery.save(MasteryState(learner_id, topic, 5))
    assert get_next_question(learner_id, topic, mastery, questions, attempts).question_id == "exact"
    attempts.values[(learner_id, "exact")] = {"passed": True}
    assert get_next_question(learner_id, topic, mastery, questions, attempts).question_id == "near-high"


def test_completed_topic_returns_none_and_does_not_repeat():
    learner_id, topic = "learner-1", Topic.STRINGS
    questions = Questions([make_question("a", topic, 3), make_question("b", topic, 4)])
    attempts, mastery = Attempts(), Mastery()
    attempts.values.update({(learner_id, "a"): {}, (learner_id, "b"): {}})
    assert get_next_question(learner_id, topic, mastery, questions, attempts) is None


def test_learner_and_demo_quotas_exhaust_and_fail_closed():
    learners = Learners()
    demo = {"execution_submissions": 0, "generation_attempts": 0}
    assert all(consume_execution_quota(learners, "learner-1", demo) for _ in range(5))
    assert consume_execution_quota(learners, "learner-1", demo) is False
    assert demo["execution_submissions"] == 5
    assert all(consume_generation_quota(learners, "learner-1", demo) for _ in range(2))
    assert consume_generation_quota(learners, "learner-1", demo) is False

    demo["execution_submissions"] = 40
    assert consume_execution_quota(learners, "other", demo) is False
    assert consume_execution_quota(learners, "other", {"execution_submissions": "bad"}) is False
