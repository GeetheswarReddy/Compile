# Compile

Compile is an adaptive Python practice demo: a fixed five-question baseline, practice at the learner’s current mastery, a four-level hint ladder, verified question generation, and optional private audio reflections. Anonymous progress is tied to the identity stored in the browser.

## Develop and verify

Use Python 3.12 (the deployed runtime), Node 22, and AWS SAM CLI.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix frontend
.venv/bin/python -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
sam validate --lint --template-file infra/template.yaml
sam build --template-file infra/template.yaml
```

Copy `frontend/.env.example` to `frontend/.env` for local development, then run `npm run dev --prefix frontend`. That example targets the existing AWS API; real submissions consume the demo budget. Tests use emulated AWS services and do not touch the account. The Linux-only kernel restriction test runs in CI and is skipped on macOS.

`Makefile` and `scripts/build_lambda.py` package only `backend/`, `scripts/`, `seed/`, and `infra/`. Local environments, frontend dependencies, logs, and credentials are excluded. Lambda supplies boto3; development dependencies are never packaged.

## Update the existing backend

The active stack is **compile-v2**, Region **ap-southeast-2**. Preserve the stack and its data; do not delete and recreate it for a code update.

```bash
sam build --template-file infra/template.yaml
sam deploy --template-file .aws-sam/build/template.yaml \
  --config-file "$PWD/samconfig.toml" \
  --stack-name compile-v2 --region ap-southeast-2 --resolve-s3
```

Review the change set and approve the update. The template adds a quota table and a private execution Lambda in a VPC with no internet route, no DNS, and a deny-all network ACL. The executor has no database, S3, or Bedrock permissions. API and verification functions invoke it privately; learner code does not run inside their privileged processes. Linux child restrictions additionally deny network/process creation syscalls and apply time/memory limits. This is a bounded anonymous demo, not an authenticated production learning service.

Generation uses `amazon.nova-lite-v1:0` by default. Its role permits `bedrock:InvokeModel`, as required by the [Converse API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html). The browser waits eight seconds before loading the nearest seed; the worker continues for up to three candidates and can retain a late verified question. Prepared questions expire after 30 minutes and must remain within one point of mastery when selected. Exact duplicate prompts/reference implementations are rejected; semantic originality is requested from the model but is not a formal guarantee.

After the stack reaches `UPDATE_COMPLETE`, run the bounded smoke test. It creates a fresh learner and uses six shared execution submissions:

```bash
.venv/bin/python scripts/smoke_api.py \
  --api-url https://j8ftz443b9.execute-api.ap-southeast-2.amazonaws.com/v1
```

Then verify generation and an audio upload/playback/delete in the hosted browser. Passing local tests or SAM validation alone does not establish live Bedrock access, IAM wiring, S3 browser behavior, or Lambda execution correctness.

## Amplify frontend

The existing app is `d17lwbfv0m80so`, branch `main`, connected to the GitHub repository. The root `amplify.yml` defines the monorepo app root `frontend`, uses `npm ci`, and publishes `frontend/dist`. Configure literal environment values, not YAML variable aliases:

```text
AMPLIFY_MONOREPO_APP_ROOT=frontend
VITE_API_BASE_URL=https://j8ftz443b9.execute-api.ap-southeast-2.amazonaws.com/v1
VITE_DEMO_TRACE=true
```

The following command previews the required settings. Add `--apply` to update the existing app after approving the change:

```bash
.venv/bin/python scripts/configure_amplify.py \
  --app-id d17lwbfv0m80so \
  --api-url https://j8ftz443b9.execute-api.ap-southeast-2.amazonaws.com/v1
```

It configures a `404-200` rewrite from `/<*>` to `/index.html` for direct `/baseline` and `/practice/arrays` navigation. It does not push Git or trigger a build. **The repository owner performs `git push`**; Amplify then builds that commit. The intended frontend URL is `https://main.d17lwbfv0m80so.amplifyapp.com`.

## Demo limits and recordings

DynamoDB transactions enforce a shared ceiling of **40 executions** and **20 generation requests**, and learner ceilings of **five practice checks** and **two generation requests**. Baseline submissions and candidate verification consume the shared execution budget, leaving the five learner practice checks available after calibration. Storage errors fail closed. Exhausting either shared ceiling disables both execution and generation; reading learning material remains available.

Budgets do not reset automatically. An operator can reset the `execution_submissions` and `generation_attempts` attributes on the `quotaId=demo` record in the stack’s `QuotasTable`. Learner counters live separately in `LearnersTable`; a shared reset does not reset individual limits. Stop active demo traffic before an intentional reset.

Recordings use presigned PUT/GET URLs, a private encrypted S3 bucket, browser CORS, a 30-day lifecycle, and metadata TTL. Playback URLs last 15 minutes; expired metadata cannot issue new playback URLs. Replacing a recording requires explicit confirmation; delete removes its object and metadata immediately. The anonymous browser identity acts as the access key: clearing browser storage loses access to its progress and recordings.

## Structure

```text
backend/          Domain services, AWS adapters, private executor
frontend/         React/Vite client
infra/            SAM template and generation state machine
seed/             Thirty verified seed exercises
scripts/          Runtime packaging, Amplify configuration, API smoke test
tests/            Contract, execution, persistence, and integration tests
.github/workflows/ Linux Python 3.12 and frontend checks
```
