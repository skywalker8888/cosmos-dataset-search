# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.visual_search.config import settings
from src.visual_search.v1.apis.bulk_indexing import router as BulkIndexingApiRouter
from src.visual_search.v1.apis.collections import router as CollectionsApiRouter
from src.visual_search.v1.apis.document_indexing import (
    router as DocumentIndexingApiRouter,
)
from src.visual_search.v1.apis.linear_probe import router as LinearProbeApiRouter
from src.visual_search.v1.apis.milvus_admin import router as MilvusAdminApiRouter
from src.visual_search.v1.apis.pipelines import router as PipelinesApiRouter
from src.visual_search.v1.apis.search import router as SearchApiRouter
from src.visual_search.v1.apis.search_refinement import (
    router as SearchRefinementApiRouter,
)

app = FastAPI(
    title="Dear Saigon",
    description=(
        "Service for indexing and querying of collections of video data for RAG applications"
    ),
    version="1.1.0",
    contact={
        "name": "#sw-cvcore-visual-search",
        "url": "https://nvidia.com",
    },
    openapi_tags=settings.openapi_tags,
    debug=settings.debug,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Any time any a path operation encounters errors validating a request (e.g.,
    deserializing a JSON payload into a ``pydantic`` dataclass), this function is run.

    ``fastapi``'s default behavior includes the body of the request in exceptions, which
    risks leaking sensitive information into logs.

    This approach attempts to avoid that, while still preserving enough information that
    error messages are helpful for debugging and for differentiating between root causes.

    Notes
    -----

    * description of this approach: https://fastapi.tiangolo.com/tutorial/handling-errors/
    """
    # TODO: could be simplified if https://github.com/tiangolo/fastapi/discussions/10934 happens
    errors = []
    for err in exc.errors():
        if isinstance(err, dict):
            err.pop("input", None)
        errors.append(err)
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": err}),
    )


app.include_router(CollectionsApiRouter)
app.include_router(DocumentIndexingApiRouter)
app.include_router(LinearProbeApiRouter)
app.include_router(SearchApiRouter)
app.include_router(SearchRefinementApiRouter)
app.include_router(PipelinesApiRouter)
app.include_router(MilvusAdminApiRouter)
app.include_router(BulkIndexingApiRouter)

# /metrics endpoint scraped by Prometheus
Instrumentator().instrument(app).expose(app, tags=["Metrics"])
