# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def clean_server_env(monkeypatch):
    """Keep a developer shell's LLAMA_SERVER_URL from leaking into default-URL tests."""
    monkeypatch.delenv("LLAMA_SERVER_URL", raising=False)
