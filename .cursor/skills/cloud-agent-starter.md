# Cloud Agent Starter Skill: Run + Test CDS

Use this as the default runbook when a Cloud agent needs to run, debug, or test this repository.

## 1) Fast bootstrap (do this first)

1. Authenticate to NGC container registry:
   - `docker login nvcr.io`
   - Username: `$oauthtoken`
   - Password: your `NVIDIA_API_KEY`
2. Prepare env file:
   - `cp deploy/standalone/.env.example deploy/standalone/.env`
   - Set at least:
     - `NVIDIA_API_KEY=...`
     - `DATA_DIR=...` (create it first: `mkdir -p <DATA_DIR>`)
3. Ensure LocalStack hostname mapping exists:
   - `echo "127.0.0.1   localstack" | sudo tee -a /etc/hosts`
4. Install Python deps + CLI:
   - `make install`
5. Build and start stack:
   - `make build-docker`
   - `make test-integration-up`
6. Basic health checks:
   - `curl http://localhost:8888/health`
   - `curl http://localhost:9000/v1/health/ready`
   - `curl http://localhost:8888/v1/pipelines`

If NGC auth or GPU is unavailable, skip full-stack bring-up and use unit-test workflows in sections 3 and 4.

## 2) Common env toggles ("feature flags" and mocks)

Use these in `deploy/standalone/.env` to quickly reproduce or isolate issues:

- `ALLOWED_PIPELINES=cosmos_video_search_milvus`  
  Limit enabled pipelines to reproduce pipeline-availability issues.
- `VISUAL_SEARCH_LOG_LEVEL=DEBUG`  
  Increase API-side logs for debugging.
- `NIM_TRITON_LOG_VERBOSE=1` and/or `NIM_LOG_LEVEL=INFO`  
  Increase Cosmos-embed logs when model/startup issues appear.
- `MAX_DOCS_PER_UPLOAD=100`  
  Lower batch sizes to test indexing edge cases.
- `GUNICORN_WORKERS=1`  
  Force single worker for deterministic debugging.
- `AWS_ENDPOINT_URL=http://localstack:4566`  
  Keep storage mocked through LocalStack (default local mode).
- `CDS_API_URL`, `CDS_CDN_URL`, `CDS_UI_URL`  
  Set these when UI is accessed from a remote host instead of localhost.

After debugging, reset overrides back to defaults in `.env` before final verification.

## 3) Area: Deployment + integration (`deploy/`, `docker/`, service wiring)

Use when changes touch compose files, startup, env wiring, or service communication.

Recommended workflow:

1. Start stack: `make test-integration-up`
2. Run integration checks: `make test-integration-run`
3. Inspect runtime logs if needed: `make test-integration-logs`
4. Targeted logs:
   - `docker compose -f deploy/standalone/docker-compose.build.yml logs visual-search`
   - `docker compose -f deploy/standalone/docker-compose.build.yml logs cosmos-embed`
   - `docker compose -f deploy/standalone/docker-compose.build.yml logs milvus`

Reset options:

- Soft reset: `make test-integration-down`
- Full cleanup/reset: `make test-integration-clean` then `make test-integration-up`

## 4) Area: Backend/API (`src/visual_search`)

Use when editing FastAPI endpoints, pipeline config, ingestion/retrieval, or API internals.

Fast test workflow:

1. Targeted unit tests:
   - `make test-specific-local TEST=src/visual_search/tests/test_retrieval.py`
   - `make test-specific-local TEST=src/visual_search/tests/test_collections.py`
   - `make test-specific-local TEST=src/visual_search/tests/test_cosmos_document_indexing.py`
2. Broader backend suite:
   - `make test-visual-search-local`
3. Optional API smoke on running stack:
   - `curl http://localhost:8888/health`
   - `curl http://localhost:8888/v1/collections`

## 5) Area: Retrieval components (`src/haystack`) and models (`src/models`)

Use when changing haystack components, serialization, Milvus adapters, or model code.

Test workflow:

1. Haystack tests:
   - `make test-haystack-local`
2. Model tests:
   - `make test-models-local`
3. If uncertain, run all unit groups:
   - `make test-unit-local`

## 6) Area: CLI + end-user flows (`src/visual_search/client`, API contracts)

Use when changing CLI behavior, API payloads, or ingestion/search command UX.

Test workflow:

1. Install CLI bits:
   - `make install-cds-cli`
   - `source .venv/bin/activate`
2. Avoid interactive config in agents; write config directly:
   - `mkdir -p ~/.config/cds`
   - create `~/.config/cds/config`:
     - `[default]`
     - `api_endpoint = http://localhost:8888`
     - `[local]`
     - `api_endpoint = http://localhost:8888`
3. Smoke commands:
   - `cds pipelines list --profile local`
   - `cds collections list --profile local`
4. Optional ingestion/search smoke:
   - `make ingest-msrvtt-small`
   - `cds search --collection-ids <collection-id> --text-query "person walking" --top-k 3 --profile local`

## 7) Area: Web UI behavior (containerized UI, API integration)

Use when validating user-visible flows or API/UI contract behavior.

Test workflow:

1. Ensure stack is up: `make test-integration-up`
2. Open UI: `http://localhost:8080/cosmos-dataset-search`
3. Validate:
   - pipeline and collection dropdowns load
   - text search returns results
   - (if data exists) video previews and download links resolve
4. Record a quick walkthrough video for non-trivial UI-related changes.

## 8) Keep this skill current (important)

Whenever you discover new runbook knowledge, update this file in the same PR:

1. Add the tip under the relevant area section.
2. Include:
   - trigger/symptom
   - exact command(s)
   - expected "success" output
   - cleanup/reset command if stateful
3. Prefer shortest reliable workflow; remove superseded steps instead of stacking duplicates.
