# Advanced Endpoints Reference

Endpoint reference for API surface not covered by the
[REST API User Guide](api-user-guide.md) tutorial. Every field below is
derived from the route decorator, handler body, and Pydantic model — not
from the endpoint name.

> **Security.** No endpoint on this page performs authentication or
> authorization. The handlers do not document or enforce authentication.
> Deployments must provide access control externally. See
> [API Security and Deployment Model](api-security.md).

All paths are relative to the `/v1` mount point, e.g.
`http://localhost:8888/v1/insert-data`.

---

## POST /insert-data

### Purpose

Starts an asynchronous Milvus bulk import of Parquet files into an existing
collection. The endpoint validates each file's Parquet schema against the
target collection schema, then submits one Milvus bulk-insert task per file.

It does **not** embed or transform data. The Parquet files must already
contain vectors matching the collection schema.

### Security

No authentication. The `cds` client sets an `Authorization: Bearer <token>`
header when a token is configured
(`src/visual_search/client/io_utils.py`), but no server-side code reads
that header. It is accepted and ignored.

### Request

`Content-Type: application/json`

No path or query parameters.

#### Body — `InsertDataRequest`

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `collection_name` | string | yes | — | Collection ID or name. Normalized through `create_safe_name()` before use. |
| `parquet_paths` | array of string | yes | — | Must each be `s3://bucket/key.parquet`. See path handling below. |
| `access_key` | string | no | `null` | Object-storage access key ID. |
| `secret_key` | string | no | `null` | Object-storage secret key. |
| `endpoint_url` | string (URL) | no | `null` | S3-compatible endpoint, e.g. MinIO. Typed `HttpUrl`, so a malformed URL fails schema validation with `422`. |

The model defines no minimum length on `parquet_paths`. An empty array
passes validation, performs no work, and falls through to
`500 Milvus did not return a job ID`.

### Response

`202 Accepted` — `InsertDataResponse`

| Field | Type | Notes |
|---|---|---|
| `status` | string | Handler always emits `"success"`. |
| `message` | string | Handler always emits `"Data insertion started"`. |
| `job_id` | string | **Only the first job ID.** See below. |

> The model's OpenAPI examples show `"accepted"` and `"Bulk data insertion
> job accepted and started."`. The handler does not use those values; it
> returns the literals above. Trust the handler, not the example.

### Errors

| Status | Condition |
|---|---|
| `400` | Parquet schema does not match the collection schema (`MilvusServiceError`). |
| `400` | Collection's pipeline is disabled or unknown. Detail lists enabled pipelines. |
| `400` | A path is not of the form `s3://bucket/key`. |
| `404` | Collection does not exist. Body is `{"detail": "Collection not found"}`, raised by `get_collections()`. |
| `404` | A Parquet file was not found during schema validation. |
| `422` | Request body failed schema validation. |
| `500` | Milvus returned no job ID for a submitted file. |

The handler contains a second, unreachable 404 with the message
`Collection {id} does not exist`; `get_collections()` raises its own 404
first, so that string is never emitted.

### Behavior and side effects

**Asynchronous.** A `202` means the import tasks were *submitted*, not that
data is queryable. Poll `GET /job-status/{job_id}` or `GET /jobs`.

**One job per file, but only one ID returned.** The handler loops over
`parquet_paths`, calling Milvus once per file and collecting every job ID —
then returns `job_ids[0]` only. If you submit five files you get five
Milvus tasks and one trackable ID. **Recover the rest via `GET /jobs`;
they are otherwise unreachable.** Prefer one file per request if you need
per-file tracking.

**Submission is not atomic.** Schema validation runs across all files
first, but S3-path format is checked *inside* the submission loop. A
malformed path at position 3 returns `400` after positions 1 and 2 have
already been submitted to Milvus. Those imports continue running. A `400`
from this endpoint does not mean nothing happened.

**Credentials are request-scoped.** `access_key` / `secret_key` are passed
to Milvus for that call and not persisted by this handler.

### Example

#### Request

```bash
curl -X POST http://localhost:8888/v1/insert-data \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "my-collection",
    "parquet_paths": ["s3://cosmos-test-bucket/embeddings/batch-01.parquet"],
    "access_key": "test",
    "secret_key": "test",
    "endpoint_url": "http://localhost:4566"
  }'
```

#### Response

```json
{
  "status": "success",
  "message": "Data insertion started",
  "job_id": "451284977899261234"
}
```

---

## GET /job-status/{job_id}

### Purpose

Returns the current state of a single Milvus bulk-insert task, searching
every enabled pipeline's Milvus store until the task is found.

### Security

No authentication. Job IDs are Milvus task IDs and are not scoped to a
caller — any client can read any job's status.

### Request

`GET /v1/job-status/{job_id}`

#### Parameters

| Name | In | Type | Required | Notes |
|---|---|---|---|---|
| `job_id` | path | string | yes | Declared as `str`, but cast with `int()` in the handler. Must be numeric. |

No query parameters, no body.

### Response

`200 OK` — `JobStatusResponse`

| Field | Type | Populated here | Notes |
|---|---|---|---|
| `job_id` | string | yes | Echoes the path parameter as given. |
| `status` | string | yes | One of `pending`, `in_progress`, `persisted`, `completed`, `failed`, `failed_cleaned`, `unknown`. |
| `details` | string | yes | Milvus `failed_reason` if set, otherwise the raw state name. |
| `progress` | integer or null | **no** | Always `null` from this endpoint. |
| `collection_name` | string or null | **no** | Always `null` from this endpoint. |

**This endpoint returns status only, never progress.** Both `progress` and
`collection_name` exist on the model but are not set by this handler. For
percentage progress and the target collection, use `GET /jobs`.

### Errors

| Status | Condition |
|---|---|
| `404` | No enabled pipeline's Milvus store recognizes the ID. Detail: `Bulk insert job {job_id} not found`. |
| `500` | A Milvus error other than "can't find task". Detail names the pipeline. |
| `500` | `job_id` is non-numeric — `int(job_id)` raises `ValueError`, which is unhandled. |

A non-numeric ID produces `500`, not `404` or `422`. Validate client-side.

### Behavior and side effects

Read-only. The handler walks enabled pipelines in order; a "can't find
task" error moves to the next pipeline, and only exhausting all of them
yields `404`. Pipelines with no Milvus store are skipped.

### Example

#### Request

```bash
curl http://localhost:8888/v1/job-status/451284977899261234
```

#### Response

```json
{
  "job_id": "451284977899261234",
  "status": "completed",
  "details": "ImportCompleted",
  "progress": null,
  "collection_name": null
}
```

---

## GET /jobs

### Purpose

Lists bulk-insert tasks aggregated across every enabled pipeline's Milvus
store. This is the only way to recover job IDs that `POST /insert-data`
did not return.

### Security

No authentication. Returns tasks for **all** collections by default, not
just the caller's — collection names and job states across the whole
deployment are readable by any client that can reach the port.

### Request

`GET /v1/jobs`

#### Parameters

| Name | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `limit` | query | integer | no | `null` (unlimited) | Passed to each store *and* applied again to the merged list. See below. |
| `collection_name` | query | string | no | `null` (all) | Normalized via `create_safe_name()` before matching. |

No path parameters, no body.

### Response

`200 OK` — array of `JobDetail`. `JobDetail` extends `JobStatusResponse`:

| Field | Type | Populated here | Notes |
|---|---|---|---|
| `job_id` | string | yes | Milvus task ID. |
| `status` | string | yes | Same vocabulary as `/job-status`. |
| `details` | string | yes | `failed_reason`, else state name. |
| `progress` | integer or null | yes | Percentage, when Milvus reports it. |
| `collection_name` | string or null | yes | Target collection. |
| `parquet_paths` | array of string | rarely | See note below — expect `[]`. |
| `row_count` | integer or null | **no** | On the model; not set by this handler. |
| `create_time_utc` | integer or null | **no** | On the model; not set by this handler. |
| `last_update_time_utc` | integer or null | **no** | On the model; not set by this handler. |

An empty array is a valid, successful response.

> **`parquet_paths` is usually empty.** The handler assigns
> `t.files if isinstance(t.files, list) else []`. For the pinned pymilvus
> version, `BulkInsertState.files` is documented as a comma-separated
> string, which fails the `isinstance` check and yields `[]`. Do not build
> clients that depend on this field being populated, and do not assume it
> discloses file paths — confirm against your deployment before relying on
> either behavior.

### Errors

**Milvus listing exceptions are suppressed and still produce `200`.** A
`MilvusException` while listing a store's tasks is logged as a warning and
that pipeline is skipped; the response returns `200` with whatever the
remaining pipelines yielded. A Milvus outage is therefore
indistinguishable from "no jobs exist" — do not treat `[]` as proof that
no import is running.

The handler itself raises no `HTTPException`, but the endpoint is not
exempt from the usual failure modes:

| Status | Condition |
|---|---|
| `422` | FastAPI query validation, e.g. `?limit=abc` — rejected before the handler runs. |
| `500` | Unhandled errors during response construction or model validation. |

### Behavior and side effects

Read-only.

**`limit` is applied twice and is not a reliable page size.** It is passed
to each store's `list_bulk_insert_tasks()`, then the merged list is
truncated to `limit` again. With N pipelines you may see up to N × `limit`
rows fetched before truncation, and which rows survive depends on pipeline
iteration order. There is no pagination, cursor, or total count.

Tasks with `task_id == 0` are filtered out as stale.

### Example

#### Request

```bash
curl "http://localhost:8888/v1/jobs?limit=2&collection_name=my-collection"
```

#### Response

```json
[
  {
    "job_id": "451284977899261234",
    "status": "completed",
    "details": "ImportCompleted",
    "progress": 100,
    "collection_name": "my-collection",
    "parquet_paths": ["embeddings/batch-01.parquet"],
    "row_count": null,
    "create_time_utc": null,
    "last_update_time_utc": null
  }
]
```

---

## POST /linear_probe

> **Deprecated and non-functional.** The route's own OpenAPI summary is
> `[DEPRECATED] Train a linear probe.` It additionally fails at collection
> resolution and normally returns an unhandled `500` — see "Behavior and
> side effects" below. Use `POST /search_refinement/train`. Documented here
> so the failure is understood rather than rediscovered.

### Purpose

**Training only — it performs no retrieval.** Given grounding queries and
labelled examples, it fits a linear model whose weights live in the
embedding space, and returns those weights as query embeddings. It does not
search, rank, or return documents.

To use the result, pass a returned embedding as an `EmbeddingQuery` to a
search endpoint in a second call.

### Security

No authentication. The module imports `Depends` from FastAPI but never
applies it; no dependency is attached to the route.

### Request

`Content-Type: application/json`

No path or query parameters.

#### Body — `LinearProbeRequest`

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `grounding_queries` | array of query objects | yes | — | Union of `TextQuery`, `VideoQuery`, `EpisodeQuery`, `EmbeddingQuery`. `TextQuery.text` must be non-empty; `EmbeddingQuery.embedding` must be a non-empty tuple. |
| `labels` | array of `LabelledDocuments` | yes | — | Must be non-empty. Collection names must be unique across entries. |
| `regularization_strength` | float | no | `0.05` | Must be `>= 0`. **Has no effect — see below.** |

`LabelledDocuments`:

| Field | Type | Required | Notes |
|---|---|---|---|
| `collection_name` | string | yes | Collection ID. |
| `labelled_documents` | object (string → boolean) | yes | Document ID → `true` (good retrieval) or `false` (bad retrieval). |

> **`regularization_strength` is accepted, validated, and then discarded.**
> The handler calls `run_linear_probe_pipeline()` without passing it, so the
> pipeline's own default of `0.05` always applies. Sending any other value
> changes nothing. This is a defect, not intended behavior — do not rely on
> the field.

### Response

`200 OK` — `LinearProbeResponse`

| Field | Type | Notes |
|---|---|---|
| `queries` | array of `EmbeddingQuery` | Each has an `embedding` array of floats, dimensioned to the pipeline's embedding space. |

### Errors

**In practice, expect `500`** — see the defect note below. `422` from
request-body schema validation is reached, because that runs before the
handler. The statuses below are what the handler *would* emit, and are
listed for completeness rather than as behavior you can rely on:

| Status | Condition |
|---|---|
| `422` | Request body failed schema validation, or a model validator raised `InputValidationError`. Reached — runs before the handler. |
| `404` | Collection lookup failed. `{"detail": "Collection not found"}` from `get_collections()`, or `Requested collections {...} not found!`. |
| `422` | Requested collections span more than one pipeline type. |
| `422` | The resolved query pipeline does not expose exactly one document store. |
| `422` | One or more labelled document IDs do not exist in their collection. |

The route declares `400` in its OpenAPI `responses` block, but no code path
in the handler produces `400`. Validation failures surface as `422`.

### Behavior and side effects

Stateless with respect to the collection: it reads document embeddings and
returns model weights. Nothing is written, and the trained probe is **not
persisted** — it exists only in the response. There is no probe ID and no
way to retrieve it later.

Embeddings are fetched with `return_embedding=True`, so requests over large
label sets pull full vectors into memory.

> **This endpoint is effectively broken and normally returns an unhandled
> `500`.** Do not build against it. Use `POST /search_refinement/train`.
>
> Two compounding defects in collection resolution:
>
> 1. `get_collections()` is annotated `-> List[Collection]` but returns a
>    single `Collection` — it constructs `Collection(**collection[0])` and
>    discards the rest. `test_get_collections_with_two_ids_returns_first`
>    in `src/visual_search/tests/test_collections.py` pins this behavior.
> 2. The handler calls `list_collections()` and passes the resulting
>    `Collection` **objects** into `get_collections()`, which expects
>    string IDs, then iterates the single returned model:
>    `[c for c in get_collections(lookup)]`.
>
> Failure normally occurs at one of two points. `get_collections()` may
> reject the `Collection` objects it was handed in place of ID strings,
> surfacing as a lookup error. If it does return a model, iterating it
> yields `(field_name, value)` tuples, so `collections` becomes a list of
> tuples and the first attribute access — `collection.id`, inside the
> `missing = ...` generator — raises `AttributeError`. Either way execution
> fails before any training occurs, surfacing as `500` rather than the
> `404` the route advertises.

### Example

#### Request

```bash
curl -X POST http://localhost:8888/v1/linear_probe \
  -H "Content-Type: application/json" \
  -d '{
    "grounding_queries": [{"text": "picture of a cat"}],
    "labels": [
      {
        "collection_name": "d51c9157-e6c5-46cf-9b29-1dd7a9a1febe",
        "labelled_documents": {
          "f0bdff82-4b90-4776-82dd-54f130861dfc": true,
          "0f2334a1-2a08-4e77-9c14-2e906dce6e4c": false
        }
      }
    ]
  }'
```

#### Response

Shape only. This is the response model's structure, **not** what the
endpoint currently returns — as documented above, the request above will
normally fail with `500` before producing this. Vector values and
dimensionality depend on the pipeline's embedding model and cannot be
derived from the code.

```json
{
  "queries": [
    { "embedding": [0.0131, -0.0074, 0.0298, "... (embedding-dim floats)"] }
  ]
}
```

---

## POST /search_refinement/train

### Purpose

Trains a search-refinement model from labelled retrieval examples and
returns it. Supersedes `POST /linear_probe`.

**Training only — it performs no retrieval.** Two model types are
supported, selected by `model_type`:

- `linear_probe` — fits a linear model in embedding space and returns its
  weights as query embeddings, to be fed back into a search call.
- `linear_classifier` — trains a scikit-learn classifier and returns its
  coefficients **plus a serialized copy of the model object**.

### Security

No authentication.

> **The `linear_classifier` response contains a pickled Python object.**
> `model` is a base64-encoded `pickle.dumps()` payload
> (`_serialize_model()`, protocol 5). Unpickling can execute arbitrary code
> — the format permits it, so a tampered payload is a code-execution
> vector. Because this endpoint is unauthenticated and served over plain
> HTTP in the bundled Compose deployment, a client that unpickles the
> response trusts both the server and the network path. Treat the `model`
> field as untrusted input: do not unpickle it in a privileged process, and
> prefer reconstructing from `weights` where possible.

### Request

`Content-Type: application/json`

No path or query parameters.

#### Body — `SearchRefinementRequest`

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `model_type` | string enum | no | `"linear_probe"` | One of `linear_probe`, `linear_classifier`. |
| `grounding_queries` | array of query objects | yes | — | `TextQuery` \| `VideoQuery` \| `EpisodeQuery` \| `EmbeddingQuery`. Ignored when `model_type` is `linear_classifier`. |
| `labels` | array of `LabelledDocuments` | yes | — | Must be non-empty; collection names unique. |
| `regularization_strength` | float | no | `0.05` | Must be `>= 0`. Applies to `linear_probe` only. |

Unlike `/linear_probe`, this handler **does** forward
`regularization_strength` to the pipeline, so the value takes effect.

### Response

`200 OK`. The schema depends on `model_type`:

`linear_probe` → `LinearProbeResponse`

| Field | Type |
|---|---|
| `queries` | array of `EmbeddingQuery` |

`linear_classifier` → `LinearClassifierResponse`

| Field | Type | Notes |
|---|---|---|
| `weights.coef` | array of arrays of float | Classifier coefficients. |
| `weights.intercept` | array of float | Intercept terms. |
| `model` | string | Base64-encoded pickle. See the security note above. |

### Errors

Reachable in practice:

| Status | Condition |
|---|---|
| `422` | Request body failed schema validation, or a model validator raised `InputValidationError`. Includes an unrecognized `model_type`, which the enum rejects. |
| `404` | Collection does not exist. `{"detail": "Collection not found"}`, raised inside `get_collections()`. |
| `422` | The resolved query pipeline does not expose exactly one document store. |
| `422` | One or more labelled document IDs do not exist in their collection. |
| `500` | **More than one distinct collection in `labels` — see below.** |

Declared but **unreachable**:

| Status | Why it never fires |
|---|---|
| `501` | The `else` branch for an unimplemented `model_type` cannot be reached: `model_type` is typed as the `SearchRefinementMode` enum, so any value outside `linear_probe` / `linear_classifier` is rejected with `422` during request validation, before the handler runs. |
| `404` | The handler's own `Requested collections {...} not found!` sits inside the `len(collections) != len(collection_ids)` branch. Because `get_collections()` returns a single collection that the handler wraps into a one-element list, that branch is only entered when N > 1 — where it raises `TypeError` first. The 404 line is never reached. |
| `422` | Likewise for the mixed-pipeline check: `collections` always holds exactly one entry, so `pipeline_types` can never contain more than one value. |
| `400` | Declared in the route's OpenAPI `responses` block; no handler path produces it. |

### Behavior and side effects

Nothing is persisted. The trained model exists only in the response — there
is no model ID and no way to retrieve it later. Re-training requires
re-sending the labels.

Embeddings are fetched with `return_embedding=True`, so large label sets
pull full vectors into memory.

> **Multi-collection training is broken and returns an unhandled `500`.**
> `get_collections()` is annotated `-> List[Collection]` but returns a
> single `Collection`. The handler compensates with
> `if not isinstance(collections, list): collections = [collections]`,
> which yields a one-element list regardless of how many IDs were
> requested. When `labels` references N > 1 distinct collections, the guard
> `len(collections) != len(collection_ids)` is true, and the next line
> evaluates `collection_ids - set(...)` — a `list` minus a `set`, which
> raises `TypeError: unsupported operand type(s)`. This is unhandled and
> surfaces as `500`, not the `404` the branch intends.
>
> **Send labels for exactly one collection per request.** The
> single-collection path (`1 == 1`) skips the broken branch and works.

### Example

#### Request

```bash
curl -X POST http://localhost:8888/v1/search_refinement/train \
  -H "Content-Type: application/json" \
  -d '{
    "model_type": "linear_probe",
    "grounding_queries": [{"text": "picture of a cat"}],
    "labels": [
      {
        "collection_name": "d51c9157-e6c5-46cf-9b29-1dd7a9a1febe",
        "labelled_documents": {
          "f0bdff82-4b90-4776-82dd-54f130861dfc": true,
          "0f2334a1-2a08-4e77-9c14-2e906dce6e4c": false
        }
      }
    ],
    "regularization_strength": 0.05
  }'
```

#### Response

Shape only — vector values and dimensionality depend on the pipeline's
embedding model.

```json
{
  "queries": [
    { "embedding": [0.0131, -0.0074, 0.0298, "... (embedding-dim floats)"] }
  ]
}
```

---

## POST /retrieval

### Purpose

Runs one search across **multiple collections** and returns the merged
result set. `POST /collections/{collection_id}/search` is the
single-collection equivalent.

### Security

No authentication. The caller names the collections, and any collection ID
in the deployment is queryable.

### Request

`Content-Type: application/json`

No path or query parameters.

#### Body — `RetrievalQuery`

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `collections` | array of string | yes | — | Collection IDs. Unknown IDs are **silently skipped** — see below. |
| `query` | query object | yes | — | Any `QueryType`: `TextQuery`, `VideoQuery`, `EpisodeQuery`, `SessionSegmentQuery`, `SessionFrameQuery`, or `EmbeddingQuery` — or a list of these for a batch query. |
| `params` | `TopKSearch` \| `RadiusSearch` | yes | — | `RadiusSearch` is rejected with `422`. |
| `payload_keys` | array of string or null | no | `()` | Metadata projection. **The default strips all metadata** — see below. |
| `generate_asset_url` | boolean | no | `true` | Whether to generate asset URLs. |
| `rerank` | boolean | no | `true` | Merged re-ranking; requires a single pipeline type. |

The model is `frozen = True`, so instances are immutable server-side.

### Response

`200 OK` — `SearchResponse` with a `retrievals` array. Each entry carries
`content`, `score`, `metadata`, `mime_type`, `embedding`, and the source
`collection_id`.

### Errors

| Status | Condition |
|---|---|
| `422` | `params` is a `RadiusSearch`. Detail: `Radius search is currently not implemented.` |
| `400` | Mixed pipelines during re-ranking. Requires **all three**: `rerank` is true, the merged result set holds more than one entry, and the queried collections span more than one pipeline type. A mixed-pipeline query that returns 0 or 1 results succeeds. |
| `400` | A key in `payload_keys` is absent from a result's metadata. Detail: `Key {key} not found in metadata.` |
| `422` | Request body failed schema validation. |

**No `404` is emitted**, despite the route declaring one. Unknown
collection IDs are filtered out by `[c for c in lookup if c.id in
retrieval_query.collections]` and contribute nothing. A request naming only
nonexistent collections returns `200` with an empty `retrievals` array.

### Behavior and side effects

Read-only.

> **`payload_keys` defaults to stripping all metadata.** The field's
> default is `()` — an empty *tuple*. The handler returns full metadata
> only when the value `is None`, and clears it when the value `== []`.
> An empty tuple satisfies neither (`() == []` is `False` in Python), so it
> falls through to the projection branch, which iterates nothing and
> assigns `{}`. **To receive metadata you must send `"payload_keys": null`
> explicitly, or name the keys you want.** Omitting the field returns
> results with empty `metadata` objects.

Re-ranking sorts the merged list in descending order and is applied only
when more than one result is present.

Metadata projection is applied row-by-row in Python. The handler carries an
in-source note that this does not scale to large result sets, since every
row is scanned per requested key.

### Example

#### Request

```bash
curl -X POST http://localhost:8888/v1/retrieval \
  -H "Content-Type: application/json" \
  -d '{
    "collections": ["my-collection", "archive-collection"],
    "query": {"text": "a person riding a bicycle"},
    "params": {"nb_neighbors": 5},
    "payload_keys": null,
    "rerank": true
  }'
```

#### Response

Shape only — field values depend on indexed content.

```json
{
  "retrievals": [
    {
      "collection_id": "my-collection",
      "content": "",
      "score": 0.8123,
      "metadata": { "source_id": "clip-0042" },
      "mime_type": "video/mp4",
      "embedding": null,
      "asset_url": "http://localhost:4566/cosmos-test-bucket/clip-0042.mp4"
    }
  ]
}
```

---

## POST /admin/collections/{collection_id}/flush

### Purpose

Seals the collection's growing segments and persists them to Milvus'
storage backend, then attempts to load the collection, rather than waiting
for Milvus' background flush scheduler.

Intended for operational and test use — for example, forcing durability
after an ingest.

> **Flush does not by itself establish search visibility.** In Milvus,
> whether newly written data is visible to a query is governed by the
> **consistency level** of that query, not by having flushed. Flushing
> persists sealed segments; it is not a substitute for requesting a
> stronger consistency level if you need read-your-writes behavior. See
> the [Milvus performance FAQ](https://milvus.io/docs/v2.4.x/performance_faq.md).

### Security

No authentication. See the warning in
[API Security and Deployment Model](api-security.md).

This route does resolve FastAPI dependencies (`GetCollection`,
`GetPipeline`), but those perform collection lookup, not identity checks.
Their presence is not authentication.

### Request

`POST /v1/admin/collections/{collection_id}/flush`

#### Parameters

| Name | In | Type | Required | Notes |
|---|---|---|---|---|
| `collection_id` | path | string | yes | Must match `^[a-zA-Z0-9_-]+$`, max length 100. Enforced by FastAPI; violations return `422`. |

No query parameters, no body.

### Response

`200 OK` — `FlushResponse`

| Field | Type | Notes |
|---|---|---|
| `id` | string | The collection ID as resolved. |
| `flushed_at` | string (date-time) | `datetime.utcnow()` at completion — naive UTC, no offset suffix. |
| `message` | string | Defaults to `"Collection flushed successfully."` |

### Errors

| Status | Condition |
|---|---|
| `404` | Collection does not exist (raised during dependency resolution). |
| `404` | Collection resolved, but its pipeline has no Milvus document store. Detail: `No Milvus document store found for this collection.` |
| `422` | `collection_id` violates the path pattern or length limit. |
| `500` | The Milvus flush call failed. Detail: `Flush failed: {exc}`. |

This endpoint resolves a **single** collection ID, so the
`get_collections()` list/single mismatch that breaks `/linear_probe` and
multi-collection `/search_refinement/train` does not affect it.

### Behavior and side effects

**Synchronous and blocking.** Unlike `/insert-data`, this call does not
return a job ID. It blocks until Milvus persists the sealed segment, then
attempts `load()` to make it searchable.

**A failed reload does not fail the request.** If `load()` raises, the
exception is caught and logged as a warning; the endpoint still returns
`200`. A success response therefore does not guarantee the collection was
reloaded — only that the flush completed.

**Not data-destroying, but not free.** Flush persists data rather than
removing it. It is nonetheless a state-changing administrative operation:
each call seals segments, and repeated invocation produces many small
segments that degrade query performance and consume storage. An
unauthenticated caller can invoke it in a loop against any collection.

The handler iterates every document store in the index pipeline and
flushes each Milvus store it finds; the first failure aborts with `500`,
potentially after earlier stores have already been flushed.

### Example

#### Request

```bash
curl -X POST http://localhost:8888/v1/admin/collections/my-collection/flush
```

#### Response

```json
{
  "id": "my-collection",
  "flushed_at": "2026-08-08T09:41:22.118374",
  "message": "Collection flushed successfully."
}
```

---

## GET /pipelines/draw/{name}

### Purpose

Renders a pipeline's processing graph as a PNG image, in either index or
query mode. Diagnostic aid for understanding how a pipeline is wired.

### Security

No authentication.

> **Verify before enabling this in a restricted network.** Rendering is
> delegated to Haystack's `Pipeline.draw()`. Haystack 2.x has historically
> produced these diagrams by calling an external rendering service rather
> than drawing locally, which would mean the pipeline graph leaves your
> network on each request. This could not be confirmed from this
> repository — `haystack-ai` is a third-party dependency and its source is
> not vendored here. **Confirm the behavior of the pinned version
> (`haystack-ai==2.11.2`) in your deployment before exposing this endpoint
> from an air-gapped or egress-restricted environment.**

### Request

`GET /v1/pipelines/draw/{name}`

#### Parameters

| Name | In | Type | Required | Default | Notes |
|---|---|---|---|---|---|
| `name` | path | string | yes | — | Pipeline ID. No pattern restriction is applied. |
| `mode` | query | string enum | no | `index` | One of `index`, `query`. |

No body.

### Response

`200 OK` with `Content-Type: image/png` and the raw PNG bytes as the body.

**This endpoint does not return JSON.** Clients that assume a JSON body
will fail to parse it.

### Errors

| Status | Condition |
|---|---|
| `404` | Pipeline does not exist or is disabled. Detail: `Requested pipeline {name} does not exist or is disabled!` |
| `422` | `mode` is not `index` or `query`. |

The handler catches `KeyError` only. Rendering failures that raise anything
else propagate as `500`.

### Behavior and side effects

Read-only with respect to collections and pipelines.

Rendering writes a temporary PNG under `/tmp` via
`tempfile.TemporaryDirectory`, which is removed when the request
completes. Each call re-renders; there is no caching.

### Example

#### Request

```bash
curl -o pipeline.png \
  "http://localhost:8888/v1/pipelines/draw/cosmos_video_search_milvus?mode=query"
```

#### Response

Binary PNG data. Inspect with:

```bash
file pipeline.png
# pipeline.png: PNG image data, 1234 x 567, 8-bit/color RGBA, non-interlaced
```
