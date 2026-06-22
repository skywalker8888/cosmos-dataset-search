# AGENTS.md

## Cursor Cloud specific instructions

NVIDIA Cosmos Dataset Search (CDS) is a single, GPU-oriented product for semantic
video search: a FastAPI orchestration service (`visual-search`) in front of a
Milvus vector DB, a Cosmos-embed NIM embedding microservice, and S3-compatible
object storage, plus a `cds` client CLI. Standard commands live in the `Makefile`,
`pyproject.toml` (`[project.scripts]`), and `README.md` / `docs/docs/` — reference
those rather than duplicating them.

### Environment basics
- Python package manager is **`uv`** (lockfile `uv.lock`). The project targets
  **Python 3.10**, while the system Python is newer — always use the `.venv`
  created by uv (`uv venv .venv --python 3.10`), not system Python.
- The update script already runs `make install` equivalent (`uv sync --all-extras`
  + `uv pip install -e ".[client]"`). After it runs, activate with
  `source .venv/bin/activate`. `torch` installs as the CPU-usable `2.6.0+cu118`
  build (`torch.cuda.is_available()` is `False` in CPU-only cloud VMs).

### Lint and tests (CPU-only, no extra services)
- Lint is driven by **pre-commit** (`.pre-commit-config.yaml`), which only lints
  *changed* files. The whole tree is not flake8-clean under the raw hook args, so
  run lint on your diff, not `flake8 src/` over everything. A full `pre-commit run
  --all-files` will also fail because non-Python hooks (clang-format, go, terraform,
  buildifier) need toolchains that are not installed here.
- Unit tests: `make test-unit-local` (runs the visual_search, haystack, and models
  suites). These pass on CPU with no external services.

### Running the service WITHOUT GPU / Docker / NGC (dev + smoke testing)
The full production stack (`make build-docker` + `make test-integration-up`) needs
an **NVIDIA GPU**, an **NGC `NVIDIA_API_KEY`**, and **Docker** — none of which exist
in a CPU-only cloud VM, so that path cannot run here.

You can still boot the FastAPI service standalone and exercise core
collection-management functionality using **embedded Milvus Lite** (pure-CPU,
ships with `pymilvus[milvus_lite]`):

- A pipeline is only marked `enabled` when ALL of its mustache env vars are present.
  For the bundled `cosmos_video_search_milvus` pipeline, set:
  - `MILVUS_DOCUMENT_STORE_URI` to a local file path (e.g. `/workspace/.milvus_lite/cds.db`)
    → this makes `MilvusClient` use embedded Milvus Lite on CPU.
  - `MILVUS_DB=default`
  - `COSMOS_EMBED_NIM_URI=http://localhost:9000` — a dummy URL is fine. The embedder
    only contacts the NIM when video/text is actually embedded, not at pipeline load,
    so the service starts and collection CRUD works without a real NIM/GPU.
- Start it: `GUNICORN_PORT=8888 <those env vars> visual-search` (gunicorn binds
  `0.0.0.0:$GUNICORN_PORT`, default 8000). Swagger UI: `http://localhost:8888/v1/docs`,
  health: `GET /health`.
- **Milvus Lite gotcha:** local mode only supports `FLAT`, `IVF_FLAT`, `AUTOINDEX`
  index types. Creating a collection via the REST API with the default (empty)
  `index_config` works (AUTOINDEX), but the `cds collections create` CLI defaults to
  `GPU_CAGRA` and will return HTTP 500 from the index step (the registry row is still
  written). Pass `--index-type IVF_FLAT` to the CLI to create collections cleanly on
  CPU. With real GPU Milvus, use the default GPU indexes.

### cds CLI
- Configure `~/.config/cds/config` with a profile, e.g. `[local]` →
  `api_endpoint = http://localhost:8888`, then run `cds pipelines list --profile local`,
  `cds collections list --profile local`, `cds collections create ... --profile local`.
