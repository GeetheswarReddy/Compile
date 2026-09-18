import json
from datetime import datetime, timezone

from backend.reflection import create_reflection, delete_reflection


class FakeRepository:
    def __init__(self):
        self.items = {}
        self.deleted = []

    def get(self, learner_id, question_id):
        return self.items.get((learner_id, question_id))

    def save(self, learner_id, question_id, metadata):
        value = {**metadata, "learnerId": learner_id, "questionId": question_id}
        self.items[(learner_id, question_id)] = value
        return value

    def delete(self, learner_id, question_id):
        self.deleted.append((learner_id, question_id))
        self.items.pop((learner_id, question_id), None)


class FakeS3:
    def __init__(self):
        self.presigns = []
        self.deleted = []

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):
        self.presigns.append((operation, Params, ExpiresIn))
        return "https://upload.example.test/presigned"

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs)


def event(question_id="q1", body=None):
    return {
        "headers": {"X-Learner-Id": "learner-1"},
        "pathParameters": {"questionId": question_id},
        "body": json.dumps(body or {"contentType": "audio/webm"}),
    }


def test_create_issues_upload_metadata_with_thirty_day_expiry(monkeypatch):
    monkeypatch.setenv("REFLECTION_BUCKET", "private-reflections")
    repository, s3 = FakeRepository(), FakeS3()
    current = datetime(2026, 9, 18, 12, tzinfo=timezone.utc)

    result = create_reflection(event(), None, repository, s3, current)
    payload = json.loads(result["body"])

    assert result["statusCode"] == 201
    assert payload["uploadUrl"] == "https://upload.example.test/presigned"
    assert datetime.fromisoformat(payload["expiresAt"]) == datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    assert s3.presigns[0][0] == "put_object"
    assert s3.presigns[0][1]["ContentType"] == "audio/webm"
    assert repository.get("learner-1", "q1")["s3Key"] == payload["s3Key"]


def test_replacement_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setenv("REFLECTION_BUCKET", "private-reflections")
    repository, s3 = FakeRepository(), FakeS3()
    repository.save("learner-1", "q1", {"s3Key": "old-key"})

    result = create_reflection(event(body={"contentType": "audio/webm"}), None, repository, s3)

    assert result["statusCode"] == 409
    assert s3.deleted == []
    assert repository.get("learner-1", "q1")["s3Key"] == "old-key"


def test_confirmed_replacement_deletes_old_audio_and_metadata(monkeypatch):
    monkeypatch.setenv("REFLECTION_BUCKET", "private-reflections")
    repository, s3 = FakeRepository(), FakeS3()
    repository.save("learner-1", "q1", {"s3Key": "old-key"})

    result = create_reflection(
        event(body={"contentType": "audio/mp4", "confirmReplacement": True}),
        None,
        repository,
        s3,
    )

    assert result["statusCode"] == 201
    assert s3.deleted == [{"Bucket": "private-reflections", "Key": "old-key"}]
    assert repository.deleted == [("learner-1", "q1")]
    assert repository.get("learner-1", "q1")["contentType"] == "audio/mp4"


def test_delete_removes_audio_and_metadata(monkeypatch):
    monkeypatch.setenv("REFLECTION_BUCKET", "private-reflections")
    repository, s3 = FakeRepository(), FakeS3()
    repository.save("learner-1", "q1", {"s3Key": "recording-key"})

    result = delete_reflection(event(), None, repository, s3)

    assert result["statusCode"] == 204
    assert s3.deleted == [{"Bucket": "private-reflections", "Key": "recording-key"}]
    assert repository.get("learner-1", "q1") is None
