"""Generation entry point and the AWS Step Functions definition.

The module deliberately keeps AWS construction at the edge.  The state machine
does the retrying; candidate verification and persistence live in
``generation_handlers`` so they can be invoked directly in tests and locally.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from .contracts import Topic
from .quota import consume_generation_quota

MAX_CANDIDATES = 3
CANDIDATE_TIMEOUT_SECONDS = 2
GENERATION_TIMEOUT_SECONDS = 8


def generation_state_machine_definition(
    candidate_generator_arn: str = "${GenerateCandidateArn}",
    candidate_handler_arn: str = "${HandleGeneratedCandidateArn}",
) -> dict[str, Any]:
    """Return the ASL definition owned by this ticket.

    A task timeout is the per-candidate budget.  Step Functions' ``MaxAttempts``
    counts retries after the initial task, so it is two for three total
    candidates.
    """
    return {
        "Comment": "Compile verified question generation",
        "StartAt": "GenerateCandidate",
        "TimeoutSeconds": GENERATION_TIMEOUT_SECONDS,
        "States": {
            "GenerateCandidate": {
                "Type": "Task",
                "Resource": candidate_generator_arn,
                "TimeoutSeconds": CANDIDATE_TIMEOUT_SECONDS,
                "Retry": [{
                    "ErrorEquals": ["States.ALL"],
                    "MaxAttempts": MAX_CANDIDATES - 1,
                    "BackoffRate": 1.0,
                    "IntervalSeconds": 0,
                }],
                "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "Fallback"}],
                "Next": "HandleGeneratedCandidate",
            },
            "HandleGeneratedCandidate": {
                "Type": "Task",
                "Resource": candidate_handler_arn,
                "TimeoutSeconds": CANDIDATE_TIMEOUT_SECONDS,
                "Retry": [{
                    "ErrorEquals": ["States.ALL"],
                    "MaxAttempts": MAX_CANDIDATES - 1,
                    "BackoffRate": 1.0,
                    "IntervalSeconds": 0,
                }],
                "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "Fallback"}],
                "Next": "CandidateResult",
            },
            "CandidateResult": {
                "Type": "Choice",
                "Choices": [
                    {"Variable": "$.status", "StringEquals": "accepted", "Next": "Succeed"},
                    {"Variable": "$.status", "StringEquals": "stale", "Next": "Stale"},
                    {
                        "And": [
                            {"Variable": "$.status", "StringEquals": "retry"},
                            {"Variable": "$.attemptState.attempt", "NumericLessThan": MAX_CANDIDATES},
                        ],
                        "Next": "NextAttempt",
                    },
                ],
                "Default": "Fallback",
            },
            "NextAttempt": {
                "Type": "Pass",
                "Parameters": {"attempt.$": "States.MathAdd($.attempt, 1)"},
                "ResultPath": "$.attemptState",
                "Next": "GenerateCandidate",
            },
            "Fallback": {"Type": "Task", "Resource": candidate_handler_arn, "Parameters": {"fallback": True, "learnerId.$": "$.learnerId", "topic.$": "$.topic"}, "End": True},
            "Stale": {"Type": "Succeed"},
            "Succeed": {"Type": "Succeed"},
        },
    }


# Short aliases are useful to IaC adapters and preserve a discoverable public
# interface if the factory is referred to as ``step_functions_definition``.
step_functions_definition = generation_state_machine_definition
build_state_machine_definition = generation_state_machine_definition


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("body", event)
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    raise ValueError("generation request body must be a JSON object")


def _learner_id(event: Mapping[str, Any], body: Mapping[str, Any]) -> str:
    headers = event.get("headers") or {}
    value = next((v for k, v in headers.items() if k.lower() == "x-learner-id"), None)
    value = value or body.get("learnerId") or event.get("learnerId")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("X-Learner-Id is required")
    return value


def _topic(body: Mapping[str, Any], event: Mapping[str, Any]) -> Topic:
    value = body.get("topic") or event.get("topic") or (event.get("pathParameters") or {}).get("topicId")
    try:
        return value if isinstance(value, Topic) else Topic(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("topic is required and must be a supported topic") from exc


def start_generation(
    event: Mapping[str, Any],
    context: Any,
    learner_repository: Any | None = None,
    demo_quota: Any = None,
    step_functions_client: Any | None = None,
    state_machine_arn: str | None = None,
) -> dict[str, Any]:
    """Consume generation quota and start one Step Functions execution."""
    del context
    body = _body(event)
    learner_id, topic = _learner_id(event, body), _topic(body, event)
    if learner_repository is None:
        table_name = os.environ.get("LEARNERS_TABLE", "compile-learners")
        import boto3  # pragma: no cover - supplied by Lambda
        from .repositories import LearnerRepository
        learner_repository = LearnerRepository(boto3.resource("dynamodb").Table(table_name))
    if not consume_generation_quota(learner_repository, learner_id, demo_quota):
        return {"statusCode": 429, "body": json.dumps({"error": "generation quota exhausted"})}
    if step_functions_client is None:
        import boto3  # pragma: no cover - supplied by Lambda
        step_functions_client = boto3.client("stepfunctions")
    arn = state_machine_arn or os.environ.get("GENERATION_STATE_MACHINE_ARN")
    if not arn:
        raise RuntimeError("GENERATION_STATE_MACHINE_ARN is not configured")
    payload = {"learnerId": learner_id, "topic": topic.value, "mastery": body.get("mastery"), "requestId": event.get("requestId")}
    result = step_functions_client.start_execution(stateMachineArn=arn, input=json.dumps(payload))
    return {"statusCode": 202, "body": json.dumps({"executionArn": result.get("executionArn"), "topic": topic.value})}


__all__ = [
    "MAX_CANDIDATES", "CANDIDATE_TIMEOUT_SECONDS", "GENERATION_TIMEOUT_SECONDS",
    "generation_state_machine_definition", "step_functions_definition",
    "build_state_machine_definition", "start_generation",
]
