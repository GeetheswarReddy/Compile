"""API-boundary regressions using the deployed seed format and DynamoDB engine."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from backend import api_adapters as api
from backend.contracts import LearnerState, MasteryState, PreparedQuestion, Topic
from backend.dependencies import compose_dependencies
from backend.execution_runner import run_submission, verify_question
from backend.generation_handlers import _candidate_value, handle_generated_candidate
from backend.repositories import _question_from_item
from scripts.seed_questions import _dynamo_item


@pytest.fixture
def deps(monkeypatch):
    with mock_aws():
        monkeypatch.setenv('AWS_DEFAULT_REGION', 'ap-southeast-2')
        db = boto3.resource('dynamodb')
        schemas = {
            'LEARNERS_TABLE': ['learnerId'], 'MASTERY_TABLE': ['learnerId', 'topic'],
            'QUESTIONS_TABLE': ['questionId'], 'ATTEMPTS_TABLE': ['learnerId', 'questionId'],
            'TRACE_TABLE': ['learnerId', 'traceId'], 'REFLECTIONS_TABLE': ['learnerId', 'questionId'],
            'PREPARED_QUESTIONS_TABLE': ['learnerTopic', 'questionId'], 'QUOTAS_TABLE': ['quotaId'],
        }
        for name, keys in schemas.items():
            monkeypatch.setenv(name, name)
            db.create_table(TableName=name, BillingMode='PAY_PER_REQUEST',
                AttributeDefinitions=[{'AttributeName': k, 'AttributeType': 'S'} for k in keys],
                KeySchema=[{'AttributeName': k, 'KeyType': 'HASH' if i == 0 else 'RANGE'} for i, k in enumerate(keys)])
        corpus = json.loads(Path('seed/questions.json').read_text())
        for question in corpus['questions']:
            db.Table('QUESTIONS_TABLE').put_item(Item=_dynamo_item(question, corpus['version']))
        result = compose_dependencies(dynamodb=db, s3=object(), bedrock=object(), stepfunctions=object())
        result['executor'] = run_submission
        monkeypatch.setattr(api, 'compose_dependencies', lambda: result)
        yield result


def event(body=None, topic=None, learner='integration'):
    return {'headers': {'X-Learner-Id': learner, 'Origin': 'https://example.amplifyapp.com'},
            'body': json.dumps(body or {}), 'pathParameters': {'topicId': topic} if topic else {}}


def payload(response, status=200):
    assert response['statusCode'] == status, response
    assert response['headers']['Access-Control-Allow-Origin'] == '*'
    return json.loads(response['body'])


def complete_baseline(deps):
    payload(api.init_learner(event(), None))
    for index in range(5):
        current = payload(api.baseline_next(event(), None))
        assert current['progress']['answered'] == index
        public = current['question']
        assert 'hiddenTests' not in public and 'referenceSolution' not in public
        private = deps['question_repository'].get(public['questionId'])
        result = payload(api.baseline_submit(event({'questionId': private.question_id, 'code': private.reference_solution}), None))
        assert result['progress']['answered'] == index + 1
        assert result['verdict'] == {'passed': True, 'failedCases': []}
        # Duplicate requests resume without another execution charge.
        assert payload(api.baseline_submit(event({'questionId': private.question_id, 'code': private.reference_solution}), None)) == result
    assert result['completed'] and result['question'] is None


def test_baseline_resume_practice_run_check_and_trace(deps):
    payload(api.next_question(event(topic='arrays'), None), 403)
    complete_baseline(deps)
    current = payload(api.next_question(event(topic='arrays'), None))
    question = deps['question_repository'].get(current['question']['questionId'])
    checked = payload(api.run_and_check(event({'questionId': question.question_id, 'code': question.reference_solution}), None))
    assert checked['passed'] and checked['scored']
    assert checked['learner']['runCheckActions'] == 1
    second = payload(api.run_and_check(event({'questionId': question.question_id, 'code': question.reference_solution}), None))
    assert second['passed'] and not second['scored']
    assert second['mastery'] == checked['mastery']
    entries = payload(api.demo_trace(event(), None))['entries']
    assert len(entries) == 2 and entries[0]['masterySnapshot']['confidence'] == 1
    assert deps['learner_repository'].get('integration').run_check_actions == 2
    for _ in range(3):
        payload(api.run_and_check(event({'questionId': question.question_id, 'code': question.reference_solution}), None))
    exhausted = payload(api.run_and_check(event({'questionId': question.question_id, 'code': question.reference_solution}), None), 429)
    assert exhausted['readOnly']


def test_all_deployed_seed_reference_solutions_use_same_executor(deps):
    items = deps['question_repository'].table.scan()['Items']
    assert len(items) == 30
    for item in items:
        question = _question_from_item(item)
        assert verify_question(question), question.question_id


def test_fixed_baseline_rejects_out_of_order_submission_without_billing(deps):
    payload(api.init_learner(event(), None))
    q = deps['question_repository'].table.scan()['Items'][-1]
    current = payload(api.baseline_next(event(), None))['question']
    other = next(i for i in deps['question_repository'].table.scan()['Items'] if i['questionId'] != current['questionId'])
    payload(api.baseline_submit(event({'questionId': other['questionId'], 'code': other['referenceSolution']}), None), 400)
    assert deps['demo_quota'].client.get_item(TableName='QUOTAS_TABLE', Key={'quotaId': {'S':'demo'}}).get('Item') is None


def test_atomic_quota_denies_without_partial_increment(deps):
    repo, quota = deps['learner_repository'], deps['demo_quota']
    repo.save(LearnerState('quota', True))
    for _ in range(5):
        assert quota.consume('quota')
    assert not quota.consume('quota')
    item = quota.client.get_item(TableName='QUOTAS_TABLE', Key={'quotaId': {'S':'demo'}})['Item']
    assert item['execution_submissions']['N'] == '5'
    for _ in range(35):
        assert quota.consume()
    assert not quota.consume()
    assert not quota.consume('quota', 'generation')
    assert quota.exhausted()
    assert repo.get('quota').generation_requests == 0


def test_storage_failure_closes_quota(deps):
    deps['demo_quota'].table_name = 'missing'
    assert not deps['demo_quota'].consume()
    assert deps['demo_quota'].exhausted()


def test_schema_key_error_is_server_error_with_cors(deps, monkeypatch):
    monkeypatch.setattr(deps['learner_repository'], 'get', lambda _: {}['missing'])
    response = payload(api.init_learner(event(), None), 500)
    assert 'missing' not in response['error']


def test_late_generated_question_is_saved_and_retrievable_for_execution(deps):
    deps['learner_repository'].save(LearnerState('integration', True))
    deps['mastery_repository'].save(MasteryState('integration', Topic.ARRAYS, 4))
    candidate = {'topic': 'Arrays', 'difficulty': 4, 'prompt': 'Return twice the sum of the numbers.',
                 'starterCode': 'def solve(nums: list[int]) -> int:\n    pass',
                 'referenceSolution': 'def solve(nums: list[int]) -> int:\n    return 2 * sum(nums)',
                 'hiddenTests': [{'input': [[1,2]], 'expected_output': 6}, {'input': [[]], 'expected_output': 0}]}
    result = handle_generated_candidate({'learnerId':'integration', 'topic':'Arrays', 'candidate': json.dumps(candidate),
        'deadline': (datetime.now(timezone.utc)-timedelta(seconds=20)).isoformat()},
        prepared_repository=deps['prepared_repository'], question_repository=deps['question_repository'],
        mastery_repository=deps['mastery_repository'], verifier=verify_question)
    assert result['status'] == 'accepted'
    public = payload(api.next_question(event(topic='arrays'), None))['question']
    assert public['questionId'] == result['questionId']
    assert deps['question_repository'].get(public['questionId']) is not None
    assert payload(api.run_and_check(event({'questionId': public['questionId'], 'code': candidate['referenceSolution']}), None))['passed']


def test_false_zero_and_null_expected_values_survive_loader():
    for value in [False, 0, None]:
        candidate = {'topic':'Arrays','difficulty':1,'prompt':'Identity','starterCode':'def solve(x): pass',
                     'referenceSolution':'def solve(x): return x',
                     'hiddenTests':[{'input':[value],'expected_output':value}]*2}
        q = _candidate_value(json.dumps(candidate))
        assert q.hidden_tests[0].expected_output is value
        assert verify_question(q)


def test_generation_cannot_bypass_baseline_and_normalizes_topic_id(deps, monkeypatch):
    class Steps:
        def start_execution(self, **kwargs):
            self.request = json.loads(kwargs['input'])
            return {'executionArn': 'pending'}
    step = Steps()
    deps['step_functions_client'] = step
    monkeypatch.setenv('GENERATION_STATE_MACHINE_ARN', 'test-arn')
    payload(api.generate(event({'topicId': 'arrays'}), None), 403)
    deps['learner_repository'].save(LearnerState('integration', True))
    deps['mastery_repository'].save(MasteryState('integration', Topic.ARRAYS, 7))
    ack = payload(api.generate(event({'topicId': 'arrays', 'mastery': 1}), None), 202)
    assert ack['executionArn'] == 'pending' and 'question' not in ack
    assert step.request['mastery'] == 7 and step.request['topic'] == 'Arrays'
    assert step.request['attempt'] == 1


def test_completed_topic_returns_explicit_null_and_does_not_generate(deps):
    from backend.contracts import SubmissionVerdict
    deps['learner_repository'].save(LearnerState('integration', True))
    for q in deps['question_repository'].for_learner('integration'):
        if q.topic is Topic.ARRAYS:
            deps['attempt_repository'].put_scored_attempt('integration', q.question_id, SubmissionVerdict(True))
    assert payload(api.next_question(event(topic='arrays'), None))['question'] is None
    assert payload(api.generate(event({'topicId': 'arrays'}), None))['completed']
    assert deps['learner_repository'].get('integration').generation_requests == 0


def test_history_retains_attempted_questions_for_later_reflection(deps):
    from backend.contracts import SubmissionVerdict
    q = next(q for q in deps['question_repository'].for_learner('integration') if q.topic is Topic.ARRAYS)
    deps['attempt_repository'].put_scored_attempt('integration', q.question_id, SubmissionVerdict(False))
    entries = payload(api.practice_history(event(topic='arrays'), None))['entries']
    assert entries[0]['question']['questionId'] == q.question_id
    assert entries[0]['passed'] is False
    assert 'referenceSolution' not in entries[0]['question']
    assert payload(api.practice_history(event(topic='strings'), None))['entries'] == []
    assert payload(api.practice_history(event(topic='arrays', learner='another'), None))['entries'] == []
