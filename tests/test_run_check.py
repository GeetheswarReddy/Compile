import json

from backend.contracts import MasteryState, Provenance, Question, SubmissionVerdict, TestCase as DomainTestCase, Topic
from backend.run_check import run_check


class Learners:
    def __init__(self): self.values = {}
    def get(self, learner_id): return self.values.get(learner_id)
    def save(self, value): self.values[value.learner_id] = value; return value


class Attempts:
    def __init__(self): self.values = {}
    def get(self, learner_id, question_id): return self.values.get((learner_id, question_id))
    def put_scored_attempt(self, learner_id, question_id, verdict, **metadata):
        key = (learner_id, question_id)
        if key in self.values: return False
        self.values[key] = {"verdict": verdict, **metadata}; return True


class Questions:
    def __init__(self, question): self.question = question
    def get(self, question_id): return self.question if question_id == self.question.question_id else None


class Mastery:
    def __init__(self, state): self.state = state; self.saves = []
    def get(self, learner_id, topic): return self.state
    def save(self, state): self.state = state; self.saves.append(state); return state


class Trace:
    def __init__(self): self.items = []
    def append(self, learner_id, trace): self.items.append((learner_id, trace)); return "trace"


def test_only_first_check_changes_mastery_and_trace_has_provenance(monkeypatch):
    question = Question("q1", Topic.ARRAYS, 5, "prompt", "", (DomainTestCase(1, 1), DomainTestCase(2, 2)), "solve", Provenance.GENERATED)
    learners, attempts = Learners(), Attempts()
    mastery = Mastery(MasteryState("learner-1", Topic.ARRAYS, 5))
    trace = Trace()
    verdicts = iter((SubmissionVerdict(True), SubmissionVerdict(False)))
    monkeypatch.setattr("backend.run_check.run_submission", lambda question, code: next(verdicts))
    context = {"learner_repository": learners, "question_repository": Questions(question), "attempt_repository": attempts,
               "mastery_repository": mastery, "trace_repository": trace, "demo_quota": {"execution_submissions": 0}}
    event = {"headers": {"X-Learner-Id": "learner-1"}, "body": json.dumps({"questionId": "q1", "code": "x"})}

    first = run_check(event, context)
    second = run_check(event, context)

    assert json.loads(first["body"])["verdict"]["passed"] is True
    assert json.loads(second["body"])["verdict"]["passed"] is False
    assert mastery.state.score == 6
    assert len(mastery.saves) == 1
    assert trace.items[0][1]["provenance"] == "generated"
    assert trace.items[0][1]["mastery"] == 6
