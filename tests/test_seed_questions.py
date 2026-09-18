import json
from collections import Counter
from types import SimpleNamespace

from backend.contracts import Provenance, Question, TestCase, Topic, serialize_question
from scripts.seed_questions import _load_corpus, _validate_corpus, seed_questions


CORPUS_PATH = "seed/questions.json"


def test_corpus_has_required_distribution_and_private_material() -> None:
    corpus = _load_corpus(CORPUS_PATH)
    _validate_corpus(corpus)
    assert corpus["version"] == "2026.09.18"
    assert len(corpus["questions"]) == 30
    by_topic = {}
    for question in corpus["questions"]:
        by_topic.setdefault(question["topic"], []).append(question)
        assert 2 <= len(question["hidden_tests"]) <= 3
        assert question["verification"]["passed"] is True
        assert question["provenance"] == Provenance.SEEDED.value
    assert set(by_topic) == {topic.value for topic in Topic}
    for questions in by_topic.values():
        assert len(questions) == 10
        bands = Counter(
            "low" if question["difficulty"] <= 3 else "mid" if question["difficulty"] <= 7 else "high"
            for question in questions
        )
        assert bands == {"low": 3, "mid": 4, "high": 3}


def test_public_question_contract_does_not_include_execution_secrets() -> None:
    question = _load_corpus(CORPUS_PATH)["questions"][0]
    public = serialize_question(
        Question(
            question_id=question["question_id"],
            topic=Topic(question["topic"]),
            difficulty=question["difficulty"],
            prompt=question["prompt"],
            starter_code=question["starter_code"],
            hidden_tests=tuple(TestCase(case["input"], case["expected_output"]) for case in question["hidden_tests"]),
            reference_solution=question["reference_solution"],
            provenance=Provenance.SEEDED,
        )
    )
    assert "hidden_tests" not in public
    assert "reference_solution" not in public
    assert "tests" not in public


def test_seed_questions_inserts_once(monkeypatch) -> None:
    class ConditionalFailure(Exception):
        response = {"Error": {"Code": "ConditionalCheckFailedException"}}

    class FakeTable:
        def __init__(self):
            self.items = {}
            self.calls = 0

        def put_item(self, *, Item, ConditionExpression):
            assert ConditionExpression == "attribute_not_exists(questionId)"
            self.calls += 1
            if Item["questionId"] in self.items:
                raise ConditionalFailure()
            self.items[Item["questionId"]] = Item

    table = FakeTable()
    fake_boto3 = SimpleNamespace(resource=lambda name: SimpleNamespace(Table=lambda table_name: table))
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)
    assert seed_questions("questions", CORPUS_PATH) == 30
    assert seed_questions("questions", CORPUS_PATH) == 0
    assert len(table.items) == 30
    assert all("hiddenTests" in item and "referenceSolution" in item for item in table.items.values())
