"""Bounded deployed smoke test: five baseline executions, one practice check.

Uses a fresh anonymous identity, leaves its records for inspection, and never
prints reference solutions, hidden tests, credentials or presigned URLs.
"""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _safe_summary(payload):
    """Return useful live evidence without printing prompts or private code."""
    summary = {"keys": sorted(payload)}
    question = payload.get("question")
    if isinstance(question, dict):
        summary["questionId"] = question.get("questionId")
        summary["difficulty"] = question.get("difficulty")
    if isinstance(payload.get("progress"), dict):
        summary["progress"] = payload["progress"]
    for key in ("completed", "passed", "scored", "readOnly", "level"):
        if key in payload:
            summary[key] = payload[key]
    if "entries" in payload and isinstance(payload["entries"], list):
        summary["entryCount"] = len(payload["entries"])
    if "error" in payload:
        summary["error"] = payload["error"]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--origin', default='https://main.d17lwbfv0m80so.amplifyapp.com')
    parser.add_argument('--learner-id', help='Reuse a coordinated fresh identity; defaults to a random smoke identity')
    parser.add_argument('--practice-only', action='store_true', help='Resume a completed baseline and spend only one practice check')
    parser.add_argument('--sandbox-function', help='Diagnose the private executor directly without changing API quota state')
    args = parser.parse_args()
    corpus = json.loads((REPOSITORY_ROOT / 'seed/questions.json').read_text())
    solutions = {q['question_id']: q['reference_solution'] for q in corpus['questions']}
    if args.sandbox_function:
        import boto3
        from scripts.seed_questions import _dynamo_item
        question = next(q for q in corpus['questions'] if q['question_id'] == 'arrays-05')
        response = boto3.client('lambda', region_name='ap-southeast-2').invoke(
            FunctionName=args.sandbox_function,
            InvocationType='RequestResponse',
            Payload=json.dumps({
                'question': _dynamo_item(question, corpus['version']),
                'code': question['reference_solution'],
            }).encode(),
        )
        verdict = json.loads(response['Payload'].read())
        print('Private sandbox evidence:', json.dumps({
            'status': response['StatusCode'],
            'functionError': response.get('FunctionError'),
            'response': _safe_summary(verdict),
        }, sort_keys=True))
        assert not response.get('FunctionError') and verdict.get('passed') is True, verdict
        return

    learner = args.learner_id or 'smoke-' + str(uuid4())
    base = args.api_url.rstrip('/')

    def call(path, body=None, *, expected_status=200, learner_header=True):
        method = 'POST' if body is not None else 'GET'
        headers = {'Origin': args.origin}
        if learner_header:
            headers['X-Learner-Id'] = learner
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                status, response_headers, raw = response.status, response.headers, response.read()
        except HTTPError as error:
            status, response_headers, raw = error.code, error.headers, error.read()
        payload = json.loads(raw or b'{}')
        assert status == expected_status, f'{path}: HTTP {status}: {raw.decode()[:300]}'
        cors = response_headers.get('Access-Control-Allow-Origin')
        assert cors in ('*', args.origin), f'{path}: missing response CORS'
        print('Evidence:', json.dumps({
            'method': method, 'path': path, 'status': status,
            'requestId': response_headers.get('x-amzn-requestid'),
            'cors': cors, 'response': _safe_summary(payload),
        }, sort_keys=True))
        return payload

    preflight = Request(base + '/baseline/submit', method='OPTIONS', headers={
        'Origin': args.origin, 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type,x-learner-id'})
    with urlopen(preflight, timeout=15) as response:
        assert response.status == 200
        assert 'x-learner-id' in response.headers.get('Access-Control-Allow-Headers', '').lower()
        print('Evidence:', json.dumps({
            'method': 'OPTIONS', 'path': '/baseline/submit',
            'status': response.status,
            'requestId': response.headers.get('x-amzn-requestid'),
            'cors': response.headers.get('Access-Control-Allow-Origin'),
        }, sort_keys=True))
    call('/baseline/next', expected_status=400, learner_header=False)
    initialized = call('/learner/init', {})['learner']
    assert initialized['baselineCompleted'] is args.practice_only
    current = call('/baseline/next')
    if args.practice_only:
        assert current['completed'] and current['question'] is None
        print('Baseline resume/completion: passed')
    else:
        for index in range(5):
            question = current['question']
            assert 'hiddenTests' not in question and 'referenceSolution' not in question
            current = call('/baseline/submit', {'questionId': question['questionId'], 'code': solutions[question['questionId']]})
            assert current['progress']['answered'] == index + 1
            assert call('/baseline/next')['progress'] == current['progress']
        assert current['completed'] and current['question'] is None
        print('Baseline submit/resume/completion: passed')
    question = call('/topic/arrays/next-question')['question']
    if not args.practice_only:
        assert question['difficulty'] == 7, 'Passing baseline must calibrate Arrays mastery to seven'
    verdict = call('/run-check', {'questionId': question['questionId'], 'code': solutions[question['questionId']]})
    assert verdict['passed'] and verdict['scored'], verdict
    assert call('/hint', {'questionId': question['questionId'], 'currentLevel': 0})['level'] == 1
    assert call('/demo-trace')['entries']
    print('Practice, Run & Check, hint and trace: passed')
    print('Smoke learner:', learner)


if __name__ == '__main__':
    main()
