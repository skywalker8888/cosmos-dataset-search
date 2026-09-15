# API Security and Deployment Model

Read this before exposing the Visual Search API on any network other than
loopback.

> **Scope.** This document describes the *service's* security posture. To
> report a vulnerability in an NVIDIA product, see [SECURITY.md](../../SECURITY.md).

## Summary

The Visual Search API performs **no authentication or authorization of its
own**. Every endpoint is reachable by any client that can open a TCP
connection to the service port.

This is a deliberate deployment assumption, not an oversight in a single
handler: the service is designed to run behind an authenticating ingress
that terminates client identity before traffic reaches it. If you deploy it
without that ingress, every endpoint below is public.

> **Two things look like authentication and are not.** The service exposes
> `GET /callback`, tagged "OIDC callback" — it is a stub that returns the
> literal string `"OK"` and performs no token exchange or validation.
> Separately, the `cds` client sends an `Authorization: Bearer` header when
> a token is configured, which no server-side code reads. Neither
> establishes identity.

## What this means in practice

The API exposes destructive and administrative operations that are
unauthenticated in the same way read operations are:

| Endpoint | Effect if reached by an unauthenticated client |
|---|---|
| `DELETE /v1/collections/{collection_id}` | Deletes a collection and its vectors |
| `DELETE /v1/collections/{collection_id}/documents` | Deletes all documents matching a caller-supplied filter |
| `DELETE /v1/collections/{collection_id}/documents/{document_id}` | Deletes a single document |
| `POST /v1/admin/collections/{collection_id}/flush` | Forces a blocking Milvus flush — see warning below |
| `POST /v1/insert-data` | Queues a bulk ingestion job |
| `POST /v1/collections` | Creates a collection |
| `POST /v1/search_refinement/train` | Returns a pickled model object — see warning below |

There is no per-collection ownership model. Any caller that can reach the
service can read, modify, or delete any collection.

Note that the bulk document delete takes a filter and does **not** accept
an empty one: `MilvusDocumentStore.delete_documents_by_filter()` raises
`InputValidationError` for an empty filter, surfacing as `422`. It is not a
one-call "delete everything" endpoint — though a sufficiently broad filter
achieves the same result.

### Administrative flush

`POST /v1/admin/collections/{collection_id}/flush` is an **administrative
endpoint with no authentication**, and until recently was absent from the
documentation entirely. It is not data-destroying — a flush persists data
rather than removing it — but it is state-changing and abusable:

- It is **synchronous and blocking**, holding the request open until Milvus
  finishes persisting the sealed segment.
- Each call seals segments. Repeated invocation produces many small
  segments, degrading query performance and consuming storage.
- Any caller that can reach the port can invoke it, in a loop, against any
  collection.

Treat it as an operator-only route and ensure your ingress does not expose
`/v1/admin/*` to untrusted clients. Full reference:
[Advanced Endpoints](api-advanced-endpoints.md).

### Pickled model responses

`POST /v1/search_refinement/train` with `model_type: "linear_classifier"`
returns a base64-encoded Python pickle in its `model` field. The pickle
format permits arbitrary code execution during loading, so a tampered
payload is a code-execution vector.

Because the endpoint is unauthenticated and served over plain HTTP in the
bundled Compose deployment, any client that unpickles this response is
trusting both the server and the network path between them. Do not unpickle
it in a privileged process; prefer reconstructing the classifier from the
`weights` field.

## Cross-origin configuration

The service enables CORS with credentials:

```python
# src/visual_search/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_domains,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`cors_allowed_domains` currently includes a `"*"` wildcard entry alongside
the named NVIDIA UI origins. See the acknowledging comment at
`src/visual_search/config.py:27`.

**This configuration is unsupported and should be removed.** Wildcard
origins combined with `allow_credentials=True` is not a safe pairing, and
it does not fail closed.

Do not assume the browser blocks it. With `"*"` present in
`allow_origins`, Starlette treats every origin as allowed during preflight,
and **reflects the requesting origin** back on preflight and cookie-bearing
requests. (It may still emit a literal `*` on simple responses that carry
no `Cookie` header.) The practical effect is that credentialed
cross-origin requests from arbitrary origins may be permitted rather than
rejected. Treat the wildcard as potentially allowing any origin, not as an
inert misconfiguration.

Two things follow:

1. **Remove `"*"` from `cors_allowed_domains` and list origins explicitly.**
   This is the concrete fix. See `src/visual_search/config.py:27`.
2. **CORS is not access control regardless.** Non-browser clients (curl,
   SDKs, server-to-server calls) ignore it entirely. Fixing the wildcard
   removes a real browser-facing exposure; it does not authenticate
   anything.

## Deploying safely

**Do not bind the service to a public interface.** The bundled Docker
Compose file publishes ports directly:

```yaml
ports:
  - "8888:8888"   # Visual Search API
  - "8080:8080"   # Web UI
```

On a host with a public IP, this exposes both. For anything beyond local
development:

- Terminate authentication at an ingress or API gateway in front of the
  service, and ensure the service port is reachable **only** from that
  ingress.
- Bind published ports to loopback (`127.0.0.1:8888:8888`) when running
  Compose on a shared or cloud host.
- Restrict `cors_allowed_domains` to the exact UI origins you serve.
- Treat network reachability as the entire access control boundary,
  because it is.

## Error responses

The API does not return `401 Unauthorized` or `403 Forbidden` — there is no
code path that produces them. Do not write client logic that branches on
those statuses expecting this service to emit them.

Errors you will see:

| Status | Meaning |
|---|---|
| `400` | Explicit handler rejection (bad S3 path, disabled pipeline, Parquet schema mismatch) |
| `404` | Collection, document, or job not found |
| `422` | FastAPI schema validation, or `InputValidationError` raised by a model validator |
| `500` | Unhandled server error, or an upstream Milvus error |

`InputValidationError` is mapped to `422 Unprocessable Entity` by the handler
in `src/visual_search/main.py`, not to `400`.

## If you are evaluating this service for a security review

The accurate statement is: *authentication is delegated to the deployment
environment and is not implemented in the application.* Confirm the ingress
actually enforces it. An approval that assumes in-application auth would be
approving something that does not exist.
