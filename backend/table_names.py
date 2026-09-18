"""DynamoDB table names and key definitions used by the repository layer."""

from __future__ import annotations

import os


LEARNERS_TABLE = os.getenv("LEARNERS_TABLE", "compile-learners")
MASTERY_TABLE = os.getenv("MASTERY_TABLE", "compile-mastery")
QUESTIONS_TABLE = os.getenv("QUESTIONS_TABLE", "compile-questions")
ATTEMPTS_TABLE = os.getenv("ATTEMPTS_TABLE", "compile-attempts")
TRACE_TABLE = os.getenv("TRACE_TABLE", "compile-trace")
REFLECTIONS_TABLE = os.getenv("REFLECTIONS_TABLE", "compile-reflections")
PREPARED_QUESTIONS_TABLE = os.getenv("PREPARED_QUESTIONS_TABLE", "compile-prepared-questions")

# The names are intentionally kept in one place for IaC, tests, and repositories.
TABLE_NAMES = {
    "learners": LEARNERS_TABLE,
    "mastery": MASTERY_TABLE,
    "questions": QUESTIONS_TABLE,
    "attempts": ATTEMPTS_TABLE,
    "trace": TRACE_TABLE,
    "reflections": REFLECTIONS_TABLE,
    "prepared_questions": PREPARED_QUESTIONS_TABLE,
}

KEY_SCHEMAS = {
    "learners": ("learnerId",),
    "mastery": ("learnerId", "topic"),
    "questions": ("questionId",),
    "attempts": ("learnerId", "questionId"),
    "trace": ("learnerId", "traceId"),
    "reflections": ("learnerId", "questionId"),
    "prepared_questions": ("learnerTopic", "questionId"),
}

