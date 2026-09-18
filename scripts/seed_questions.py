"""Validate and idempotently deploy Compile's verified seeded questions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.contracts import Provenance, Question, TestCase, Topic


EXPECTED_TOPICS = {topic.value for topic in Topic}
EXPECTED_VERSION = "2026.09.18"


def _load_corpus(corpus_path: str) -> dict[str, Any]:
    with Path(corpus_path).open(encoding="utf-8") as corpus_file:
        corpus = json.load(corpus_file)
    if not isinstance(corpus, dict) or corpus.get("version") != EXPECTED_VERSION:
        raise ValueError(f"corpus version must be {EXPECTED_VERSION}")
    questions = corpus.get("questions")
    if not isinstance(questions, list) or len(questions) != 30:
        raise ValueError("corpus must contain exactly 30 questions")
    return corpus


def _run_cases(question: dict[str, Any]) -> None:
    namespace: dict[str, Any] = {}
    exec(question["reference_solution"], namespace)
    function = namespace.get(question["entry_point"])
    if not callable(function):
        raise ValueError(f"{question['question_id']} has no callable entry point")
    for test_case in [*question["tests"], *question["hidden_tests"]]:
        actual = function(*test_case["input"])
        if actual != test_case["expected_output"]:
            raise ValueError(
                f"{question['question_id']} reference solution failed "
                f"{test_case['input']!r}: expected {test_case['expected_output']!r}, got {actual!r}"
            )


def _validate_corpus(corpus: dict[str, Any]) -> None:
    seen_ids: set[str] = set()
    by_topic: dict[str, list[dict[str, Any]]] = {topic: [] for topic in EXPECTED_TOPICS}
    for question in corpus["questions"]:
        if not isinstance(question, dict):
            raise ValueError("each corpus question must be an object")
        question_id = question.get("question_id")
        topic = question.get("topic")
        if not isinstance(question_id, str) or not question_id or question_id in seen_ids:
            raise ValueError("question IDs must be non-empty and unique")
        if topic not in EXPECTED_TOPICS:
            raise ValueError(f"unsupported topic: {topic!r}")
        if question.get("provenance") != Provenance.SEEDED.value:
            raise ValueError(f"{question_id} must be seeded")
        hidden_tests = question.get("hidden_tests")
        tests = question.get("tests")
        if not isinstance(hidden_tests, list) or not 2 <= len(hidden_tests) <= 3:
            raise ValueError(f"{question_id} must have two or three hidden tests")
        if not isinstance(tests, list) or not tests:
            raise ValueError(f"{question_id} must have visible tests")
        for case in [*tests, *hidden_tests]:
            if not isinstance(case, dict) or not isinstance(case.get("input"), list) or "expected_output" not in case:
                raise ValueError(f"{question_id} has an invalid test case")
        verification = question.get("verification")
        if not isinstance(verification, dict) or verification.get("status") != "passed" or verification.get("passed") is not True:
            raise ValueError(f"{question_id} is not marked verified")
        Question(
            question_id=question_id,
            topic=Topic(topic),
            difficulty=question["difficulty"],
            prompt=question["prompt"],
            starter_code=question["starter_code"],
            hidden_tests=tuple(TestCase(case["input"], case["expected_output"]) for case in hidden_tests),
            reference_solution=question["reference_solution"],
            provenance=Provenance.SEEDED,
        )
        _run_cases(question)
        seen_ids.add(question_id)
        by_topic[topic].append(question)

    if set(by_topic) != EXPECTED_TOPICS or any(len(items) != 10 for items in by_topic.values()):
        raise ValueError("each topic must contain exactly ten questions")
    for topic, questions in by_topic.items():
        scores = [question["difficulty"] for question in questions]
        if sum(score <= 3 for score in scores) != 3:
            raise ValueError(f"{topic} must have three questions at difficulty 1-3")
        if sum(4 <= score <= 7 for score in scores) != 4:
            raise ValueError(f"{topic} must have four questions at difficulty 4-7")
        if sum(score >= 8 for score in scores) != 3:
            raise ValueError(f"{topic} must have three questions at difficulty 8-10")


def _dynamo_item(question: dict[str, Any], version: str) -> dict[str, Any]:
    """Build the private storage record; callers must use public serializers for API data."""

    return {
        "questionId": question["question_id"],
        "entityType": "seeded-question",
        "corpusVersion": version,
        "topic": question["topic"],
        "difficulty": question["difficulty"],
        "prompt": question["prompt"],
        "starterCode": question["starter_code"],
        "techniqueTag": question["technique_tag"],
        "provenance": question["provenance"],
        "tests": question["tests"],
        "hiddenTests": question["hidden_tests"],
        "referenceSolution": question["reference_solution"],
        "verification": question["verification"],
    }


def seed_questions(table_name: str, corpus_path: str) -> int:
    """Insert verified seed questions once and return the number newly inserted.

    DynamoDB's conditional put makes reruns safe and also prevents a concurrent
    deploy from replacing a verified record. Existing records are intentionally
    counted as zero new inserts.
    """

    if not isinstance(table_name, str) or not table_name.strip():
        raise ValueError("table_name must be a non-empty string")
    corpus = _load_corpus(corpus_path)
    _validate_corpus(corpus)

    import boto3

    table = boto3.resource("dynamodb").Table(table_name)
    inserted = 0
    for question in corpus["questions"]:
        try:
            table.put_item(
                Item=_dynamo_item(question, corpus["version"]),
                ConditionExpression="attribute_not_exists(questionId)",
            )
        except Exception as error:  # boto3 is optional until deployment and easy to fake in tests.
            if getattr(error, "response", {}).get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            continue
        inserted += 1
    return inserted


__all__ = ["seed_questions"]
