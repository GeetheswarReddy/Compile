# Compile

Compile is an adaptive Python coding-practice demo for placement preparation. A Question is served only after its reference solution has passed its executable tests.

The demo uses browser-generated anonymous identity, per-Topic Mastery, a five-Question Baseline Assessment, verified generation with Seeded Question fallback, a four-level Hint Ladder, and optional private Reflection Recordings.

## Stack

- React and Vite frontend, deployed with Amplify Hosting
- API Gateway REST API and Python 3.12 Lambda handlers
- Step Functions and Bedrock Converse for verified Question generation
- DynamoDB for learner state, Questions, attempts, traces, and recording metadata
- S3 for the Seed corpus and Reflection Recording audio

## Local setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm install --prefix frontend --no-package-lock
```

Run backend tests:

```bash
.venv/bin/python -m pytest
```

Build the frontend:

```bash
npm run build --prefix frontend
```

## Deployment

Infrastructure is defined under `infra/` using AWS SAM. Before deployment, configure AWS CLI credentials for an account and Region with access to Lambda, API Gateway, Step Functions, DynamoDB, S3, IAM, Amplify, and an enabled Bedrock model.

```bash
sam validate --template-file infra/template.yaml
sam build --template-file infra/template.yaml
sam deploy --guided
```

Use the deployed API URL in the frontend environment configuration, then deploy the `frontend/` directory through Amplify Hosting.

## Project structure

```text
backend/   Lambda domain modules
frontend/  React/Vite client
infra/     AWS SAM and Step Functions definitions
seed/      Versioned Seeded Question corpus
scripts/   Deploy-time seeding scripts
tests/     Backend test suite
tickets/   Ticket orchestration inputs and reports
```
