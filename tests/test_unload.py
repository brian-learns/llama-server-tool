# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the unload command (CLI) and the UnloadReport model."""

import httpx
import pytest
from typer.testing import CliRunner

from helpers import FakeGet, json_response
from llama_server_tool.__main__ import app
from llama_server_tool.server import ServerError
from llama_server_tool.unload import UnloadReport, unload_model

runner = CliRunner()

IDLE_SLOTS = [
    {"id": 0, "n_ctx": 8, "speculative": False, "is_processing": False},
    {"id": 1, "n_ctx": 8, "speculative": False, "is_processing": False},
]
BUSY_SLOTS = [
    {"id": 0, "n_ctx": 8, "is_processing": False},
    {"id": 1, "n_ctx": 8, "is_processing": True, "id_task": 7, "n_prompt_tokens": 42},
]
NOT_LOADED_BODY = {"error": {"code": 400, "message": "model is not loaded", "type": "invalid_request_error"}}
NOT_RUNNING_BODY = {"error": {"code": 400, "message": "model is not running", "type": "invalid_request_error"}}
NOT_FOUND_BODY = {"error": {"code": 400, "message": "model is not found", "type": "invalid_request_error"}}


def env(monkeypatch, slots, post):
    """Point the GET (slots check) and POST (unload) calls at canned fakes."""
    slots_fake = FakeGet(response=json_response(slots, status_code=200 if isinstance(slots, list) else 400))
    post_fake = FakeGet(response=json_response(post, status_code=200 if post == {"success": True} else 400))
    monkeypatch.setattr(httpx, "get", slots_fake)
    monkeypatch.setattr(httpx, "post", post_fake)
    return slots_fake, post_fake


def run_cli(monkeypatch, *args, slots=None, post=None):
    env(monkeypatch, slots, post)
    return runner.invoke(app, ["unload", *args])


def test_unload_success(monkeypatch):
    slots_fake, post_fake = env(monkeypatch, IDLE_SLOTS, {"success": True})
    report = unload_model("m")
    assert report.success is True
    assert report.model == "m"
    assert report.render() == "unload: m unloaded"
    assert slots_fake.params == {"model": "m", "autoload": "false"}  # side-effect-free check
    assert post_fake.urls == ["http://127.0.0.0:8080/models/unload"]
    assert post_fake.json_body == {"model": "m"}


def test_unload_refuses_when_busy(monkeypatch):
    slots_fake, post_fake = env(monkeypatch, BUSY_SLOTS, {"success": True})
    report = unload_model("m")
    assert report.success is False
    assert report.busy_slots == 1
    assert report.render() == "unload: m is busy (1 slot(s) processing); use --force to unload anyway"
    assert post_fake.urls == []  # refused before the POST
    assert slots_fake.params == {"model": "m", "autoload": "false"}


def test_unload_force_skips_check(monkeypatch):
    slots_fake, post_fake = env(monkeypatch, BUSY_SLOTS, {"success": True})
    report = unload_model("m", force=True)
    assert report.success is True
    assert slots_fake.urls == []  # no slots call at all
    assert post_fake.urls == ["http://127.0.0.0:8080/models/unload"]


def test_unload_not_loaded_proceeds(monkeypatch):
    """The slots check 400s (model not running, autoload=false) — the server's answer wins."""
    _, post_fake = env(monkeypatch, NOT_LOADED_BODY, {"success": True})
    report = unload_model("m")
    assert report.success is True
    assert post_fake.urls == ["http://127.0.0.0:8080/models/unload"]


def test_unload_server_error_body(monkeypatch):
    env(monkeypatch, NOT_LOADED_BODY, NOT_RUNNING_BODY)
    report = unload_model("m")
    assert report.success is False
    assert report.error is not None
    assert report.error.message == "model is not running"
    assert report.render() == "unload: model is not running"


def test_unload_not_found(monkeypatch):
    env(monkeypatch, NOT_LOADED_BODY, NOT_FOUND_BODY)
    report = unload_model("nosuchmodel")
    assert report.error is not None
    assert report.render() == "unload: model is not found"


def test_unload_unexpected_body(monkeypatch):
    post_fake = FakeGet(response=json_response({"error": "oops"}, status_code=400))
    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(NOT_LOADED_BODY, status_code=400)))
    monkeypatch.setattr(httpx, "post", post_fake)
    with pytest.raises(ServerError, match="invalid response body"):
        unload_model("m")


def test_unload_transport_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(NOT_LOADED_BODY, status_code=400)))
    monkeypatch.setattr(httpx, "post", FakeGet(error=httpx.ConnectError("connection refused")))
    with pytest.raises(ServerError, match="connection refused"):
        unload_model("m")


def test_unload_report_render_variants():
    assert UnloadReport(success=True, model="m").render() == "unload: m unloaded"
    assert UnloadReport(busy_slots=2, model="m").render() == "unload: m is busy (2 slot(s) processing); use --force to unload anyway"
    err = UnloadReport.model_validate({"error": NOT_RUNNING_BODY["error"]})
    assert err.render() == "unload: model is not running"


def test_unload_cli_success(monkeypatch):
    result = run_cli(monkeypatch, "m", slots=IDLE_SLOTS, post={"success": True})
    assert result.exit_code == 0
    assert result.output == "unload: m unloaded\n"


def test_unload_cli_not_running(monkeypatch):
    result = run_cli(monkeypatch, "m", slots=NOT_LOADED_BODY, post=NOT_RUNNING_BODY)
    assert result.exit_code == 1
    assert result.output == "unload: model is not running\n"


def test_unload_cli_busy(monkeypatch):
    result = run_cli(monkeypatch, "m", slots=BUSY_SLOTS, post={"success": True})
    assert result.exit_code == 1
    assert "unload: m is busy (1 slot(s) processing); use --force to unload anyway" in result.output


def test_unload_cli_busy_force(monkeypatch):
    result = run_cli(monkeypatch, "m", "--force", slots=BUSY_SLOTS, post={"success": True})
    assert result.exit_code == 0
    assert result.output == "unload: m unloaded\n"


def test_unload_cli_connection_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeGet(error=httpx.ConnectError("connection refused")))
    monkeypatch.setattr(httpx, "post", FakeGet(response=json_response({"success": True})))
    result = runner.invoke(app, ["unload", "m"])
    assert result.exit_code == 1
    assert "unload: connection refused" in result.stderr


def test_unload_cli_missing_model(monkeypatch):
    env(monkeypatch, IDLE_SLOTS, {"success": True})
    result = runner.invoke(app, ["unload"])
    assert result.exit_code == 2  # typer usage error: required argument missing
