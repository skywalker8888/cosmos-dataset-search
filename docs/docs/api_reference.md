# API Reference

## OpenAPI Schema

The complete OpenAPI schema is available in JSON format at:
- **File**: [openapi_schema_cvds.json](../api_reference/openapi_schema_cvds.json)
- **Live Documentation**: `http://localhost:8888/v1/docs` (when running locally)
- **Raw Schema Endpoint**: `http://localhost:8888/v1/openapi.json`

## Interactive Documentation

When the CVDS service is running, you can access the interactive API documentation:

- **Swagger UI**: `http://localhost:8888/v1/docs`
- **ReDoc**: `http://localhost:8888/v1/redoc`

## Practical Examples

For hands-on curl examples and practical usage, see the [API Guide](../guides/api.md).

## Key Endpoints Overview

The CVDS API provides the following main endpoint categories:

The 19 domain routes declared under `src/visual_search/v1/apis/`, plus the
routes registered directly on the applications. Endpoints marked **[adv]**
are documented in [Advanced Endpoints](api-advanced-endpoints.md); the rest
are covered by the [REST API User Guide](api-user-guide.md) tutorial.

### Service routes (not declared in `v1/apis`)
- `GET /health` - Service health check (root app, **not** under `/v1`)
- `GET /callback` - OIDC callback stub (root app). Returns the literal string `"OK"`; it performs no token exchange or validation.
- `GET /v1/metrics` - Prometheus scrape endpoint, registered by `prometheus-fastapi-instrumentator`

### Collection Management
- `POST /v1/collections` - Create new collection
- `GET /v1/collections` - List all collections
- `GET /v1/collections/{collection_id}` - Get collection details
- `PATCH /v1/collections/{collection_id}` - Update collection
- `DELETE /v1/collections/{collection_id}` - Delete collection

### Document Indexing
- `POST /v1/collections/{collection_id}/documents` - Index documents
- `DELETE /v1/collections/{collection_id}/documents/{document_id}` - Delete one document
- `DELETE /v1/collections/{collection_id}/documents` - Delete documents matching a filter

### Bulk Indexing
- `POST /v1/insert-data` - Start a bulk Parquet import **[adv]**
- `GET /v1/jobs` - List bulk-insert jobs across pipelines **[adv]**
- `GET /v1/job-status/{job_id}` - Status of one bulk-insert job **[adv]**

### Search & Retrieval
- `POST /v1/collections/{collection_id}/search` - Search one collection
- `POST /v1/retrieval` - Search across multiple collections **[adv]**

### Search Refinement
- `POST /v1/search_refinement/train` - Train a refinement model **[adv]**
- `POST /v1/linear_probe` - *Deprecated and non-functional* **[adv]**

### Pipeline Operations
- `GET /v1/pipelines` - List available pipelines
- `GET /v1/pipelines/{pipeline_id}/collections` - Collections for a pipeline
- `GET /v1/pipelines/draw/{name}` - Render pipeline graph as PNG **[adv]**

### Admin
- `POST /v1/admin/collections/{collection_id}/flush` - Force a Milvus flush **[adv]**

> There are **no** secrets-management endpoints. `k8s_secrets.py` and
> `nvcf_file_based_secrets_manager.py` define no routes — they provide
> secrets managers, not HTTP surface. Secrets are resolved **on demand
> during request handling**: `get_custom_aws_credentials()` in
> `src/visual_search/v1/apis/search.py` selects the NVCF file-based or
> Kubernetes manager per call, based on the `NGC_SECRETS_FILE_PATH`
> environment variable.

## Authentication

**The API implements no authentication or authorization.** This applies to
production deployments as much as to local development — every endpoint
above, including `DELETE` and `/admin/*`, is reachable by any client that
can open a connection to the port.

Access control must be enforced by the deployment environment. Read
[API Security and Deployment Model](api-security.md) before exposing this
service on any network, and see the
[AWS EKS Deployment Guide](aws-eks-deployment.md) for ingress
configuration.

## Rate Limits

See the [API Guide](../guides/api.md) for current rate limits and usage guidelines.