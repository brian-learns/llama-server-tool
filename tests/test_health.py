# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the health command (CLI) and the Health model."""

import httpx
from typer.testing import CliRunner

from llama_server_tool.__main__ import app
from llama_server_tool.health import Health, HealthError

runner = CliRunner()


class FakeGet:
    """Stand-in for httpx.get that records calls and returns a fixed response or raises."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.urls = []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.response


def json_response(body, status_code=200):
    return httpx.Response(status_code, json=body, request=httpx.Request("GET", "http://x/health"))


def run_health(monkeypatch, fake, *args):
    monkeypatch.setattr(httpx, "get", fake)
    return runner.invoke(app, ["health", *args])


def test_health_ok(monkeypatch):
    fake = FakeGet(response=json_response({"status": "ok"}))
    result = run_health(monkeypatch, fake)
    assert result.exit_code == 0
    assert "health: ok" in result.output


def test_health_503_loading_model(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    fake = FakeGet(response=json_response(body, status_code=503))
    result = run_health(monkeypatch, fake)
    assert result.exit_code == 1
    assert "health: Loading model" in result.output


def test_health_connection_error(monkeypatch):
    fake = FakeGet(error=httpx.ConnectError("connection refused"))
    result = run_health(monkeypatch, fake)
    assert result.exit_code == 1
    assert "health: connection refused" in result.stderr


def test_health_malformed_body(monkeypatch):
    fake = FakeGet(response=httpx.Response(200, text="not json", request=httpx.Request("GET", "x")))
    result = run_health(monkeypatch, fake)
    assert result.exit_code == 1
    assert "invalid response body" in result.stderr


def test_server_option_overrides_default(monkeypatch):
    fake = FakeGet(response=json_response({"status": "ok"}))
    run_health(monkeypatch, fake, "--server", "http://127.0.0.1:9999")
    assert fake.urls == ["http://127.0.0.1:9999/health"]


def test_env_var_used_without_option(monkeypatch):
    fake = FakeGet(response=json_response({"status": "ok"}))
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://env-server:1234")
    run_health(monkeypatch, fake)
    assert fake.urls == ["http://env-server:1234/health"]


def test_server_option_wins_over_env_var(monkeypatch):
    fake = FakeGet(response=json_response({"status": "ok"}))
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://env-server:1234")
    run_health(monkeypatch, fake, "--server", "http://opt-server:5678")
    assert fake.urls == ["http://opt-server:5678/health"]


def test_trailing_slash_stripped(monkeypatch):
    fake = FakeGet(response=json_response({"status": "ok"}))
    run_health(monkeypatch, fake, "--server", "http://127.0.0.1:8080/")
    assert fake.urls == ["http://127.0.0.1:8080/health"]


def test_model_renders_status():
    assert Health(status="ok").render() == "health: ok"


def test_model_renders_error():
    error = HealthError(code=503, message="Loading model", type="unavailable_error")
    assert Health(error=error).render() == "health: Loading model"


def test_model_renders_unknown_for_empty_body():
    assert Health().render() == "health: unknown response"
