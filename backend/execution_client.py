"""Invoke the private, network-isolated execution function."""
import json
import os
from .contracts import FailedCase, SubmissionVerdict
from .repositories import _question_item, _from_dynamo


def run_submission(question, code):
    import boto3
    from botocore.config import Config
    result = boto3.client("lambda", config=Config(read_timeout=12, retries={"max_attempts": 0})).invoke(
        FunctionName=os.environ["EXECUTION_FUNCTION_NAME"],
        InvocationType="RequestResponse",
        Payload=json.dumps({"question": _from_dynamo(_question_item(question)), "code": code}).encode(),
    )
    payload = json.loads(result["Payload"].read())
    if result.get("FunctionError") or "passed" not in payload:
        raise RuntimeError("execution service unavailable")
    return SubmissionVerdict(payload["passed"], tuple(
        FailedCase(c["input"], c["expected"], c["actual"]) for c in payload.get("failedCases", [])[:2]))


def verify_question(question):
    return run_submission(question, question.reference_solution).passed
