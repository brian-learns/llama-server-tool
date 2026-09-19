# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the load command (CLI) and the LoadReport model."""

import httpx
import pytest
from typer.testing import CliRunner

from helpers import FakeGet, json_response
from llama_server_tool.__main__ import app
from llama_server_tool.load import LoadReport, load_model
from llama_server_tool.server import ServerError

runner = CliRunner()

NOT_FOUND_BODY = {"error": {"code": 404, "message": "model is not found", "type": "not_found_error"}}
ALREADY_RUNNING_BODY = {"error": {"code": 400, "message": "model is already running", "type": "invalid_request_error"}}
LIMIT_BODY = {"error": {"code": 500, "message": "model limit reached, try again later", "type": "server_error"}}


def env(monkeypatch, body, status):
    """Point the POST (load) call at a canned fake."""
    post_fake = FakeGet(response=json_response(body, status_code=status))
    monkeypatch.setattr(httpx, "post", post_fake)
    return post_fake


def run_cli(monkeypatch, *args, body={"success": True}, status=200):
    post_fake = env(monkeypatch, body, status)
    return runner.invoke(app, ["load", *args]), post_fake


def test_load_success(monkeypatch):
    post_fake = env(monkeypatch, {"success": True}, 200)
    report = load_model("m")
    assert report.success is True
    assert report.model == "m"
    assert report.render() == "load: m loading"
    assert post_fake.urls == ["http://127.0.0.0:8080/models/load"]
    assert post_fake.json_body == {"model": "m"}
    assert post_fake.timeout.read == 300.0  # long default: the server may block on an LRU unload
    assert post_fake.timeout.connect == 5.0


def test_load_timeout_override(monkeypatch):
    post_fake = env(monkeypatch, {"success": True}, 200)
    load_model("m", timeout=60)
    assert post_fake.timeout.read == 60.0


def test_load_not_found(monkeypatch):
    env(monkeypatch, NOT_FOUND_BODY, 404)
    report = load_model("nosuchmodel")
    assert report.success is False
    assert report.error is not None
    assert report.error.code == 404
    assert report.render() == "load: model is not found"


def test_load_already_running(monkeypatch):
    env(monkeypatch, ALREADY_RUNNING_BODY, 400)
    report = load_model("m")
    assert report.render() == "load: model is already running"


def test_load_limit_reached(monkeypatch):
    env(monkeypatch, LIMIT_BODY, 500)
    report = load_model("m")
    assert report.error is not None
    assert report.render() == "load: model limit reached, try again later"


def test_load_unexpected_body(monkeypatch):
    env(monkeypatch, {"error": "oops"}, 400)
    with pytest.raises(ServerError, match="invalid response body"):
        load_model("m")


def test_load_transport_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", FakeGet(error=httpx.ConnectError("connection refused")))
    with pytest.raises(ServerError, match="connection refused"):
        load_model("m")


def test_load_report_render_variants():
    assert LoadReport(success=True, model="m").render() == "load: m loading"
    err = LoadReport.model_validate({"error": NOT_FOUND_BODY["error"]})
    assert err.render() == "load: model is not found"


def test_load_cli_success(monkeypatch):
    result, _ = run_cli(monkeypatch, "m")
    assert result.exit_code == 0
    assert result.output == "load: m loading\n"


def test_load_cli_not_found(monkeypatch):
    result, _ = run_cli(monkeypatch, "nosuchmodel", body=NOT_FOUND_BODY, status=404)
    assert result.exit_code == 1
    assert result.output == "load: model is not found\n"


def test_load_cli_already_running(monkeypatch):
    result, _ = run_cli(monkeypatch, "m", body=ALREADY_RUNNING_BODY, status=400)
    assert result.exit_code == 1
    assert result.output == "load: model is already running\n"


def test_load_cli_timeout_override(monkeypatch):
    _, post_fake = run_cli(monkeypatch, "m", "--timeout", "60")
    assert post_fake.timeout.read == 60.0


def test_load_cli_connection_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", FakeGet(error=httpx.ConnectError("connection refused")))
    result = runner.invoke(app, ["load", "m"])
    assert result.exit_code == 1
    assert "load: connection refused" in result.stderr


def test_load_cli_missing_model(monkeypatch):
    env(monkeypatch, {"success": True}, 200)
    result = runner.invoke(app, ["load"])
    assert result.exit_code == 2  # typer usage error: required argument missing
