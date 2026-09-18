"""CloudFormation custom resource for idempotent seeded-question population."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from scripts.seed_questions import seed_questions


def _send(event: dict, status: str, data: dict) -> None:
    response = {"Status": status, "Reason": data.get("reason", status), "PhysicalResourceId": "compile-seeded-questions", "StackId": event.get("StackId"), "RequestId": event.get("RequestId"), "LogicalResourceId": event.get("LogicalResourceId"), "Data": data}
    request = Request(event["ResponseURL"], data=json.dumps(response).encode(), method="PUT", headers={"content-type": ""})
    with urlopen(request) as result:  # nosec B310 - CloudFormation-provided URL
        result.read()


def seed(event: dict, context: object) -> dict:
    del context
    try:
        inserted = 0
        if event.get("RequestType") != "Delete":
            corpus = Path(__file__).resolve().parent.parent / "seed" / "questions.json"
            inserted = seed_questions(os.environ["QUESTIONS_TABLE"], str(corpus))
        data = {"inserted": inserted}
        if event.get("ResponseURL"):
            _send(event, "SUCCESS", data)
        return data
    except Exception as exc:
        data = {"reason": str(exc)}
        if event.get("ResponseURL"):
            _send(event, "FAILED", data)
        raise


__all__ = ["seed"]
