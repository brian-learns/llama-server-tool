# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Shared helpers for CLI tests: a fake httpx.get and a JSON response builder."""

import httpx


class FakeGet:
    """Stand-in for httpx.get that records calls and returns a fixed response or raises."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.urls = []
        self.params = None

    def __call__(self, url, timeout=None, params=None):
        self.urls.append(url)
        self.params = params
        if self.error is not None:
            raise self.error
        return self.response


def json_response(body, status_code=200):
    """Build an httpx.Response with a JSON body."""
    return httpx.Response(status_code, json=body, request=httpx.Request("GET", "http://x"))
