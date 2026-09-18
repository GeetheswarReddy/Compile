import json

from backend.contracts import MasteryState, Provenance, Question, TestCase as DomainTestCase, Topic
from backend.hints import get_next_hint


class Questions:
    def __init__(self, question): self.question = question
    def get(self, question_id): return self.question if question_id == self.question.question_id else None


class Mastery:
    def __init__(self): self.state = MasteryState("learner-1", Topic.STRINGS, 4)
    def get(self, learner_id, topic): return self.state
    def save(self, state): self.state = state; return state


def test_hints_advance_one_level_and_lower_confidence_without_verdict_state():
    question = Question("q1", Topic.STRINGS, 4, "prompt", "", (DomainTestCase("a", "a"), DomainTestCase("b", "b")), "solution", Provenance.SEEDED)
    mastery = Mastery()
    context = {"question_repository": Questions(question), "mastery_repository": mastery}
    event = {"headers": {"X-Learner-Id": "learner-1"}, "body": json.dumps({"questionId": "q1", "currentLevel": 0})}

    first = json.loads(get_next_hint(event, context)["body"])
    event["body"] = json.dumps({"questionId": "q1", "currentLevel": first["level"]})
    second = json.loads(get_next_hint(event, context)["body"])

    assert (first["level"], second["level"]) == (1, 2)
    assert mastery.state.confidence == 0.8
    assert mastery.state.score == 4
