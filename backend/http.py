"""JSON responses shared by every public Lambda handler."""
import json
from .repositories import _from_dynamo


def response(status, payload=None):
    return {"statusCode": status, "headers": {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Learner-Id",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        "Cache-Control": "no-store",
    }, "body": json.dumps(_from_dynamo(dict(payload or {})))}
