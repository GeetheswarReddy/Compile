"""Bounded deployed smoke test: five baseline executions, one practice check.

Uses a fresh anonymous identity, leaves its records for inspection, and never
prints reference solutions, hidden tests, credentials or presigned URLs.
"""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--origin', default='https://main.d17lwbfv0m80so.amplifyapp.com')
    args = parser.parse_args()
    learner = 'smoke-' + str(uuid4())
    base = args.api_url.rstrip('/')
    corpus = json.loads((Path(__file__).resolve().parents[1] / 'seed/questions.json').read_text())
    solutions = {q['question_id']: q['reference_solution'] for q in corpus['questions']}

    def call(path, body=None):
        headers = {'X-Learner-Id': learner, 'Origin': args.origin}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                assert response.headers.get('Access-Control-Allow-Origin') in ('*', args.origin), 'Missing response CORS'
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f'{path}: HTTP {error.code}: {error.read().decode()[:300]}') from error

    preflight = Request(base + '/baseline/submit', method='OPTIONS', headers={
        'Origin': args.origin, 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type,x-learner-id'})
    with urlopen(preflight, timeout=15) as response:
        assert response.status == 200
        assert 'x-learner-id' in response.headers.get('Access-Control-Allow-Headers', '').lower()
    print('Preflight: passed')
    assert not call('/learner/init', {})['learner']['baselineCompleted']
    current = call('/baseline/next')
    for index in range(5):
        question = current['question']
        assert 'hiddenTests' not in question and 'referenceSolution' not in question
        current = call('/baseline/submit', {'questionId': question['questionId'], 'code': solutions[question['questionId']]})
        assert current['progress']['answered'] == index + 1
        assert call('/baseline/next')['progress'] == current['progress']
    assert current['completed'] and current['question'] is None
    print('Baseline submit/resume/completion: passed')
    question = call('/topic/arrays/next-question')['question']
    verdict = call('/run-check', {'questionId': question['questionId'], 'code': solutions[question['questionId']]})
    assert verdict['passed'] and verdict['scored'], verdict
    assert call('/hint', {'questionId': question['questionId'], 'currentLevel': 0})['level'] == 1
    assert call('/demo-trace')['entries']
    print('Practice, Run & Check, hint and trace: passed')
    print('Smoke learner:', learner)


if __name__ == '__main__':
    main()
