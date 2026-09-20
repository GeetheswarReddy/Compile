"""Lambda handlers for private learner reflection recordings.

The handlers deliberately keep AWS construction at the edge.  Tests (and a
Lambda composition root) can pass a ReflectionRepository and an S3 client;
normal invocations lazily construct those adapters from environment config.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4

from .repositories import ReflectionRepository


REFLECTION_TTL = timedelta(days=30)
PRESIGNED_URL_EXPIRY_SECONDS = 900
_SAFE_PART = re.compile(r"^[A-Za-z0-9._~-]+$")


from .http import response as _response


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("body", {})
    if raw in (None, ""):
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        raise ValueError("body must be a JSON object")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("body must be a JSON object")
    return value


def _learner_id(event: Mapping[str, Any]) -> str | None:
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == "x-learner-id":
            return value
    return event.get("learnerId")


def _request_values(event: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    body = _body(event)
    path = event.get("pathParameters") or {}
    learner_id = _learner_id(event)
    question_id = path.get("questionId") or body.get("questionId") or event.get("questionId")
    if not isinstance(learner_id, str) or not learner_id.strip():
        raise ValueError("X-Learner-Id is required")
    if not isinstance(question_id, str) or not question_id.strip():
        raise ValueError("questionId is required")
    for value, name in ((learner_id, "learnerId"), (question_id, "questionId")):
        if not _SAFE_PART.fullmatch(value):
            raise ValueError(f"{name} contains unsupported characters")
    return learner_id, question_id, body


def _dependencies(repository: Any | None, s3: Any | None) -> tuple[Any, Any]:
    if repository is None:
        table_name = os.environ.get("REFLECTION_TABLE_NAME")
        if not table_name:
            raise RuntimeError("REFLECTION_TABLE_NAME is not configured")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - Lambda supplies boto3.
            raise RuntimeError("boto3 is required in the Lambda runtime") from exc
        repository = ReflectionRepository(boto3.resource("dynamodb").Table(table_name))
    if s3 is None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - Lambda supplies boto3.
            raise RuntimeError("boto3 is required in the Lambda runtime") from exc
        from botocore.config import Config
        s3 = boto3.client("s3", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    return repository, s3


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current


def create_reflection(
    event: Mapping[str, Any],
    context: Any,
    repository: Any | None = None,
    s3: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a presigned PUT URL and persist its private recording metadata.

    ``confirmReplacement`` is required and true when a recording already
    exists.  Existing audio and metadata are removed before the new metadata
    is written, so at most one recording remains addressable.
    """
    del context
    try:
        learner_id, question_id, body = _request_values(event)
        content_type = body.get("contentType", "audio/webm")
        if not isinstance(content_type, str) or not content_type.strip():
            raise ValueError("contentType must be a non-empty string")
        if not content_type.startswith("audio/"):
            raise ValueError("contentType must be audio")
        repository, s3 = _dependencies(repository, s3)
        existing = repository.get(learner_id, question_id)
        current = _now(now)
        existing_is_live = existing is not None and (
            not existing.get("expiresAt")
            or datetime.fromisoformat(existing["expiresAt"]) > current
        )
        if existing_is_live and body.get("confirmReplacement") is not True:
            return _response(409, {"error": "replacement requires confirmReplacement=true"})

        expires_at = current + REFLECTION_TTL
        bucket = os.environ.get("REFLECTION_BUCKET") or os.environ.get("S3_BUCKET")
        if not bucket:
            raise RuntimeError("REFLECTION_BUCKET is not configured")
        key = f"reflections/{learner_id}/{question_id}/{uuid4().hex}.audio"

        if existing is not None:
            old_key = existing.get("s3Key")
            if old_key:
                s3.delete_object(Bucket=bucket, Key=old_key)
            repository.delete(learner_id, question_id)

        upload_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )
        metadata = {
            "s3Key": key,
            "contentType": content_type,
            "createdAt": current.isoformat(),
            "expiresAt": expires_at.isoformat(),
        }
        repository.save(learner_id, question_id, metadata)
        return _response(201, {"uploadUrl": upload_url, **metadata})
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc)})


def delete_reflection(
    event: Mapping[str, Any],
    context: Any,
    repository: Any | None = None,
    s3: Any | None = None,
) -> dict[str, Any]:
    """Immediately remove both the recording object and its metadata."""
    del context
    try:
        learner_id, question_id, _ = _request_values(event)
        repository, s3 = _dependencies(repository, s3)
        existing = repository.get(learner_id, question_id)
        if existing is not None:
            bucket = os.environ.get("REFLECTION_BUCKET") or os.environ.get("S3_BUCKET")
            if not bucket:
                raise RuntimeError("REFLECTION_BUCKET is not configured")
            if existing.get("s3Key"):
                s3.delete_object(Bucket=bucket, Key=existing["s3Key"])
            repository.delete(learner_id, question_id)
        return _response(204)
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": str(exc)})


def get_reflection(event, context, repository=None, s3=None, now=None):
    try:
        learner_id, question_id, _ = _request_values(event)
        repository, s3 = _dependencies(repository, s3)
        record = repository.get(learner_id, question_id)
        current = _now(now)
        if not record or datetime.fromisoformat(record["expiresAt"]) <= current:
            return _response(200, {"reflection": None})
        remaining = max(1, min(
            PRESIGNED_URL_EXPIRY_SECONDS,
            int((datetime.fromisoformat(record["expiresAt"]) - current).total_seconds()),
        ))
        url = s3.generate_presigned_url("get_object", Params={"Bucket": os.environ["REFLECTION_BUCKET"], "Key": record["s3Key"]}, ExpiresIn=remaining)
        return _response(200, {"reflection": {"playbackUrl": url, "expiresAt": record["expiresAt"], "contentType": record["contentType"]}})
    except ValueError as exc:
        return _response(400, {"error": str(exc)})
