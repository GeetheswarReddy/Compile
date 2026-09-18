# Compile — Context Digest

## Goal

Compile is a deployed AWS demo for adaptive placement-preparation practice in Python. It only serves questions whose reference solution has passed their test cases, and retains anonymous learner progress by browser identity.

## Non-negotiable architecture

- React/Vite SPA on Amplify Hosting; no SSR.
- API Gateway REST API under `/v1`, backed by Python 3.12 Lambda functions.
- Browser-generated UUID in `localStorage` is sent in `X-Learner-Id` on every request. No accounts, Cognito, sessions, or auth headers.
- DynamoDB stores learner state, mastery, questions, attempts, Demo Trace, reflection metadata, and prepared questions. S3 stores seed corpus assets and reflection audio; reflection audio has a 30-day lifecycle rule.
- AWS Step Functions owns generation. Bedrock Converse generates candidates. Generation retries immediately at most three times, with a two-second candidate budget and an eight-second overall timeout; exhaustion/timeout returns the nearest Curated (Seeded) Question.
- `execution_runner` is the sole code-execution module. It uses a subprocess with a five-second wall-clock timeout, a 128 MB `resource.setrlimit` address-space cap, 256 MB Lambda configuration, and no outbound network permissions.
- Seeded Questions and Verification Records are inserted at deploy time and never reverified just to open the demo.
- Prepared Questions are stored separately under `learnerId#topic`, and deleted on consumption or staleness.

## Domain rules

- Topics are exactly Arrays, Strings, and Hash Maps/Two Pointers. Mastery and Difficulty Score are integers 1–10.
- Each Topic has ten Seeded Questions: three at 1–3, four at 4–7, and three at 8–10. Each Question has two or three Hidden Tests.
- Target Difficulty is current Topic Mastery; otherwise serve the nearest unattempted Question.
- Baseline is mandatory once per browser: Arrays scores 3 and 6, Strings scores 3 and 6, Hash Maps/Two Pointers score 5. Resume at the first unanswered Question.
- The first Run & Check verdict is the Scored Attempt. It changes Mastery by exactly +1 for correct or -1 for incorrect, clamped 1–10. Later checks are feedback only.
- Learner Quota is five Run & Check actions and two generation requests, then controls become read-only. Demo Quota is 40 execution submissions and 20 generation attempts, manually reset, and fails closed when exhausted.
- Generated Questions must be verified, corpus-grounded, targeted to Mastery, and materially distinct from Seeded and previously served Questions. Stale Generation is not Generation Failure.
- Hints have four learner-requested levels ending in the reference solution. Hint use lowers Mastery Confidence but never changes a verdict.
- Verdicts expose pass/fail plus at most two failed inputs with expected-versus-actual output. Never expose Hidden Tests or reference solutions in normal Question/Veredict payloads.
- Demo Trace shows provenance, retry count, and Mastery snapshot only in demo mode.
- One private Reflection Recording may exist per learner/question. It expires after 30 days, can be deleted immediately, and requires explicit confirmed deletion before replacement.
- A completed Topic does not repeat Questions or generate indefinitely.

## Backend modules and API

`learner_state.py`, `baseline.py`, `question_select.py`, `run_check.py`, `execution_runner.py`, `generation_orchestrator.py`, `hints.py`, `reflection.py`, and `quota.py` are the defined backend boundaries.

API routes: `POST /learner/init`; `GET /baseline/next`; `POST /baseline/submit`; `GET /topic/{topicId}/next-question`; `POST /run-check` with `{ questionId, code }`; `POST /generate`; `POST /hint` with `{ questionId, currentLevel }`; `POST /reflection`; `DELETE /reflection/{questionId}`; `GET /demo-trace`.

## Out of scope

Accounts/authentication, non-Python exercises, SSR, a separate container platform, startup reverification, endless question generation, and exposing Demo Trace in the future real-user experience.
