# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the Python API functions exposed at the package root."""

import json

import httpx
import pytest

from helpers import FakeGet, json_response, text_response
from llama_server_tool import (
    ApiError,
    Health,
    MetricsReport,
    ModelList,
    Props,
    ServerError,
    check_health,
    get_metrics,
    get_models,
    get_props,
)
from test_metrics import SAMPLE_TEXT
from test_models import SAMPLE_BODY as MODELS_BODY
from test_props import SAMPLE_BODY as PROPS_BODY


def with_fake(monkeypatch, fake):
    monkeypatch.setattr(httpx, "get", fake)
    return fake


def test_check_health_ok(monkeypatch):
    fake = with_fake(monkeypatch, FakeGet(response=json_response({"status": "ok"})))
    result = check_health()
    assert isinstance(result, Health)
    assert result.status == "ok"
    assert fake.urls == ["http://127.0.0.0:8080/health"]


def test_check_health_error_body_returns_model(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    with_fake(monkeypatch, FakeGet(response=json_response(body, status_code=503)))
    result = check_health()
    assert isinstance(result.error, ApiError)
    assert result.error.message == "Loading model"


def test_check_health_connection_error(monkeypatch):
    with_fake(monkeypatch, FakeGet(error=httpx.ConnectError("connection refused")))
    with pytest.raises(ServerError, match="connection refused"):
        check_health()


def test_check_health_unexpected_body(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=json_response({"error": "not-an-object"})))
    with pytest.raises(ServerError, match="invalid response body"):
        check_health()


def test_get_models(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=json_response(MODELS_BODY)))
    result = get_models()
    assert isinstance(result, ModelList)
    assert len(result.data) == 1
    assert result.data[0].id == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"


def test_get_props_builds_params(monkeypatch):
    fake = with_fake(monkeypatch, FakeGet(response=json_response(PROPS_BODY)))
    get_props(model="x")
    assert fake.params == {"model": "x", "autoload": "false"}
    get_props(model="x", autoload=True)
    assert fake.params == {"model": "x", "autoload": "true"}
    get_props()
    assert fake.params is None


def test_get_props_returns_model(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=json_response(PROPS_BODY)))
    result = get_props()
    assert isinstance(result, Props)
    assert result.model_path == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"


def test_check_health_raw(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=json_response({"status": "ok"})))
    status, body = check_health(raw=True)
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


def test_get_models_raw(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=json_response(MODELS_BODY)))
    status, body = get_models(raw=True)
    assert status == 200
    assert json.loads(body)["data"][0]["id"] == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"


def test_get_metrics_ok(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=text_response(SAMPLE_TEXT)))
    result = get_metrics()
    assert isinstance(result, MetricsReport)
    assert len(result.families) == 3
    assert result.families[0].name == "llamacpp:predicted_tokens_seconds"


def test_get_metrics_model_param(monkeypatch):
    fake = with_fake(monkeypatch, FakeGet(response=text_response(SAMPLE_TEXT)))
    get_metrics(model="Ornith-1.0-9B")
    assert fake.params == {"model": "Ornith-1.0-9B"}


def test_get_metrics_501_returns_error_model(monkeypatch):
    body = {
        "error": {
            "code": 501,
            "message": "This server does not support metrics endpoint. Start it with `--metrics`",
            "type": "not_supported_error",
        }
    }
    with_fake(monkeypatch, FakeGet(response=json_response(body, status_code=501)))
    result = get_metrics()
    assert isinstance(result.error, ApiError)
    assert "metrics endpoint" in result.error.message


def test_get_metrics_non_json_error_raises(monkeypatch):
    with_fake(monkeypatch, FakeGet(response=text_response("boom", status_code=500)))
    with pytest.raises(ServerError, match="HTTP 500: boom"):
        get_metrics()


def test_reexports_are_callable():
    for func in (check_health, get_models, get_props, get_metrics):
        assert callable(func)
    for model in (Health, ModelList, Props, MetricsReport, ApiError, ServerError):
        assert model is not None
