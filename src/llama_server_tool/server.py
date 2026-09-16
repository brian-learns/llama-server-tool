# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Shared llama-server access: URL resolution and JSON endpoint fetching."""

import os
from typing import Any

import httpx
from pydantic import BaseModel

DEFAULT_SERVER = "http://127.0.0.0:8080"
REQUEST_TIMEOUT = 5.0


class ServerError(Exception):
    """Raised when the server cannot be reached or returns an unusable response."""


class ApiError(BaseModel):
    """Standard llama-server error object, e.g. from a 503 while the model loads."""

    code: int
    message: str
    type: str


def resolve_server_url(server: str | None = None) -> str:
    """Resolve the server base URL: option, then LLAMA_SERVER_URL, then default."""
    url = server or os.environ.get("LLAMA_SERVER_URL") or DEFAULT_SERVER
    return url.rstrip("/")


def fetch_json(base: str, path: str) -> tuple[int, dict[str, Any]]:
    """GET a JSON endpoint, returning (status code, parsed body)."""
    try:
        response = httpx.get(f"{base}{path}", timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as err:
        raise ServerError(str(err)) from err
    try:
        return response.status_code, response.json()
    except ValueError as err:
        raise ServerError(f"invalid JSON from {path}: {err}") from err
