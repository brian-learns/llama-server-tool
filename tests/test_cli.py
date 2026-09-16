# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for app-level CLI behavior (no command, help output)."""

from typer.testing import CliRunner

from llama_server_tool.__main__ import app

runner = CliRunner()


def test_bare_invocation_lists_commands():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Commands" in result.output
    for name in ("health", "models", "props", "metrics"):
        assert name in result.output
