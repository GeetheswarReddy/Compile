"""Lambda dependency composition for Compile's API boundary."""

from __future__ import annotations

import os
from typing import Any

from .repositories import (
    AttemptRepository, LearnerRepository, MasteryRepository,
    PreparedQuestionRepository, QuestionRepository, ReflectionRepository,
    TraceRepository,
)


def compose_dependencies(*, dynamodb: Any | None = None, s3: Any | None = None, bedrock: Any | None = None, stepfunctions: Any | None = None) -> dict[str, Any]:
    """Construct the repositories and AWS clients used by Lambda adapters.

    Optional clients make this composition root straightforward to exercise
    with fakes; boto3 is only imported in deployed/local Lambda execution.
    """
    if dynamodb is None or s3 is None or bedrock is None or stepfunctions is None:
        import boto3  # pragma: no cover - supplied by Lambda
        dynamodb = dynamodb or boto3.resource("dynamodb")
        s3 = s3 or boto3.client("s3")
        bedrock = bedrock or boto3.client("bedrock-runtime")
        stepfunctions = stepfunctions or boto3.client("stepfunctions")
    from .quota import DynamoQuota
    from .execution_client import run_submission
    import boto3
    quota_client = boto3.client("dynamodb")
    table = lambda name: dynamodb.Table(os.environ[name])
    return {
        "learner_repository": LearnerRepository(table("LEARNERS_TABLE")),
        "mastery_repository": MasteryRepository(table("MASTERY_TABLE")),
        "question_repository": QuestionRepository(table("QUESTIONS_TABLE")),
        "attempt_repository": AttemptRepository(table("ATTEMPTS_TABLE")),
        "trace_repository": TraceRepository(table("TRACE_TABLE")),
        "reflection_repository": ReflectionRepository(table("REFLECTIONS_TABLE")),
        "prepared_repository": PreparedQuestionRepository(table("PREPARED_QUESTIONS_TABLE")),
        "s3": s3,
        "bedrock_client": bedrock,
        "step_functions_client": stepfunctions,
        "demo_quota": DynamoQuota(quota_client, os.environ["QUOTAS_TABLE"], os.environ["LEARNERS_TABLE"]),
        "executor": run_submission,
    }


__all__ = ["compose_dependencies"]
