# Final integration pass — Compile

Integrate the completed tickets without changing product decisions. Owned files: `backend/api_adapters.py`, `backend/dependencies.py`, `backend/seed_deploy.py`, `backend/generation_handlers.py`, `frontend/src/App.jsx`, `frontend/src/practice/PracticeScreen.jsx`, `infra/template.yaml`, `infra/statemachines/generation.asl.json`, `samconfig.toml`, `tests/test_integration.py`.

Tasks: create API Gateway Lambda adapters for all `/v1` domain routes and compose DynamoDB/S3/Bedrock dependencies; wire Run & Check and generation handlers; use `MasteryRepository.increment_generation_failure`; add deploy-time Seeded Question population; propagate active Question ID from PracticeScreen to hints/reflection; ensure SAM output configures frontend API URL. Run `PYTHONPATH=. .venv/bin/python -m pytest`, `npm run build --prefix frontend`, and `sam validate --template-file infra/template.yaml`. Report changed files, actual interfaces, and blockers.

Do not edit outside owned files. Never expose hidden tests/reference solutions in public payloads.
