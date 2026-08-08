# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

"""Regression tests for the CORS configuration.

The service enables ``allow_credentials=True``. Combined with a wildcard entry
in ``cors_allowed_domains`` that is not a safe configuration: Starlette treats
all origins as allowed during preflight and reflects the requesting origin back
on cookie-bearing requests, so it does not fail closed.

These tests exist so that reintroducing the wildcard breaks the build rather
than silently widening the allowed-origin set.
"""

import pytest

from src.visual_search.config import settings


def test_cors_allowed_domains_has_no_wildcard():
    """A wildcard origin must never appear in the allow-list."""
    assert "*" not in settings.cors_allowed_domains, (
        "Wildcard origin found in cors_allowed_domains. The CORS middleware "
        "sets allow_credentials=True; a wildcard there permits credentialed "
        "requests from arbitrary origins. List explicit origins instead."
    )


def test_cors_allowed_domains_entries_are_explicit_origins():
    """Every entry must be a concrete scheme://host[:port] origin."""
    for origin in settings.cors_allowed_domains:
        assert origin.startswith(("http://", "https://")), (
            f"CORS origin {origin!r} is not an explicit origin. Entries must "
            "be of the form scheme://host[:port]."
        )
        assert "*" not in origin, (
            f"CORS origin {origin!r} contains a wildcard character. Pattern "
            "matching is not supported by CORSMiddleware's allow_origins."
        )


@pytest.mark.parametrize("forbidden", ["*", "null", ""])
def test_cors_rejects_known_unsafe_origin_values(forbidden):
    """Guard against origin values that are unsafe with credentials enabled."""
    assert forbidden not in settings.cors_allowed_domains, (
        f"Unsafe origin value {forbidden!r} present in cors_allowed_domains."
    )
