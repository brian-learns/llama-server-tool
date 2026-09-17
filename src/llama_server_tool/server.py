# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Shared llama-server access: URL resolution, endpoint fetching, value formatting."""

import json
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


def format_value(value: object) -> str:
    """Format a value for reports: rounded floats, lowercase bools, comma-joined lists."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(round(value, 4))
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def fetch(base: str, path: str, params: dict[str, str] | None = None) -> tuple[int, str]:
    """GET an endpoint, returning (status code, response text)."""
    try:
        response = httpx.get(f"{base}{path}", timeout=REQUEST_TIMEOUT, params=params)
    except httpx.HTTPError as err:
        raise ServerError(str(err)) from err
    return response.status_code, response.text


def fetch_json(base: str, path: str, params: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    """GET a JSON endpoint, returning (status code, parsed body)."""
    status, text = fetch(base, path, params=params)
    try:
        return status, json.loads(text)
    except ValueError as err:
        raise ServerError(f"invalid JSON from {path}: {err}") from err


async def afetch(base: str, path: str, params: dict[str, str] | None = None) -> tuple[int, str]:
    """Async GET of an endpoint, returning (status code, response text)."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(f"{base}{path}", params=params)
        except httpx.HTTPError as err:
            raise ServerError(str(err)) from err
    return response.status_code, response.text


async def afetch_json(base: str, path: str, params: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    """Async GET of a JSON endpoint, returning (status code, parsed body)."""
    status, text = await afetch(base, path, params=params)
    try:
        return status, json.loads(text)
    except ValueError as err:
        raise ServerError(f"invalid JSON from {path}: {err}") from err
