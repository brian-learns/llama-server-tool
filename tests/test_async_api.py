# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the async Python API (aget_*) exposed at the package root."""

import asyncio
import json

import httpx
import pytest

from helpers import FakeAsyncClient, FakeGet, json_response, text_response
from llama_server_tool import (
    aget_health,
    aget_metrics,
    aget_models,
    aget_props,
    aget_slots,
    aload_model,
    aunload_model,
    check_health,
    get_metrics,
    get_models,
    get_props,
    get_slots,
    load_model,
    unload_model,
)
from llama_server_tool.server import ServerError
from llama_server_tool.slots import Slot, SlotsReport
from test_metrics import SAMPLE_TEXT
from test_models import SAMPLE_BODY as MODELS_BODY
from test_props import SAMPLE_BODY as PROPS_BODY
from test_slots import SAMPLE_BODY as SLOTS_BODY


def async_client(monkeypatch, response=None, error=None):
    """Monkeypatch server.httpx.AsyncClient with a FakeAsyncClient."""
    import llama_server_tool.server as server_module

    fake = FakeAsyncClient(response=response, error=error)

    def make_client(*a, **k):
        fake.client_timeout = k.get("timeout")
        return fake

    monkeypatch.setattr(server_module.httpx, "AsyncClient", make_client)
    return fake


def run(coro):
    return asyncio.run(coro)


def test_aget_health_ok(monkeypatch):
    fake = async_client(monkeypatch, response=json_response({"status": "ok"}))
    result = run(aget_health())
    assert result.status == "ok"
    assert fake.calls == [("http://127.0.0.0:8080/health", None)]


def test_aget_health_error_body(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    async_client(monkeypatch, response=json_response(body, status_code=503))
    result = run(aget_health())
    assert result.error is not None
    assert result.error.message == "Loading model"


def test_aget_health_connection_error(monkeypatch):
    async_client(monkeypatch, error=httpx.ConnectError("connection refused"))
    with pytest.raises(ServerError, match="connection refused"):
        run(aget_health())


def test_aget_models(monkeypatch):
    async_client(monkeypatch, response=json_response(MODELS_BODY))
    result = run(aget_models())
    assert len(result.data) == 2
    assert result.data[0].id == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"


def test_aget_models_reload(monkeypatch):
    fake = async_client(monkeypatch, response=json_response(MODELS_BODY))
    run(aget_models(reload=True))
    assert fake.calls[-1] == ("http://127.0.0.0:8080/v1/models", {"reload": "1"})


def test_aget_props_params(monkeypatch):
    fake = async_client(monkeypatch, response=json_response(PROPS_BODY))
    run(aget_props(model="x"))
    assert fake.calls[-1] == ("http://127.0.0.0:8080/props", {"model": "x", "autoload": "false"})
    run(aget_props(model="x", autoload=True))
    assert fake.calls[-1] == ("http://127.0.0.0:8080/props", {"model": "x", "autoload": "true"})
    run(aget_props())
    assert fake.calls[-1] == ("http://127.0.0.0:8080/props", None)


def test_aget_props_autoload_timeout(monkeypatch):
    fake = async_client(monkeypatch, response=json_response(PROPS_BODY))
    run(aget_props(model="x", autoload=True))
    assert fake.client_timeout.read == 300.0
    assert fake.client_timeout.connect == 5.0
    run(aget_props(model="x", autoload=True, timeout=60))
    assert fake.client_timeout.read == 60.0
    run(aget_props(model="x"))
    assert fake.client_timeout.read == 5.0


def test_aget_models_raw(monkeypatch):
    async_client(monkeypatch, response=json_response(MODELS_BODY))
    status, body = run(aget_models(raw=True))
    assert status == 200
    assert json.loads(body)["data"][0]["id"] == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"


def test_aget_metrics_ok(monkeypatch):
    async_client(monkeypatch, response=text_response(SAMPLE_TEXT))
    result = run(aget_metrics())
    assert len(result.families) == 3


def test_aget_metrics_501(monkeypatch):
    body = {
        "error": {
            "code": 501,
            "message": "This server does not support metrics endpoint. Start it with `--metrics`",
            "type": "not_supported_error",
        }
    }
    async_client(monkeypatch, response=json_response(body, status_code=501))
    result = run(aget_metrics())
    assert result.error is not None
    assert "metrics endpoint" in result.error.message


def test_aget_metrics_non_json_error(monkeypatch):
    async_client(monkeypatch, response=text_response("boom", status_code=500))
    with pytest.raises(ServerError, match="HTTP 500: boom"):
        run(aget_metrics())


def test_aget_slots(monkeypatch):
    fake = async_client(monkeypatch, response=json_response(SLOTS_BODY))
    result = run(aget_slots(model="Ornith-1.0-9B"))
    assert len(result.slots) == 2
    assert result.model_name == "Ornith-1.0-9B"
    assert fake.calls[-1] == ("http://127.0.0.0:8080/slots", {"model": "Ornith-1.0-9B"})


def test_aget_slots_non_list(monkeypatch):
    async_client(monkeypatch, response=json_response({"not": "a list"}))
    with pytest.raises(ServerError, match="failed to parse slots response"):
        run(aget_slots())


def test_aunload_model(monkeypatch):
    """Success path: the slots check is stubbed out, only the POST goes to the fake client."""
    import llama_server_tool.unload as unload_module

    async def fake_aget_slots(*args, **kwargs):
        return SlotsReport(slots=[])

    monkeypatch.setattr(unload_module, "aget_slots", fake_aget_slots)
    fake = async_client(monkeypatch, response=json_response({"success": True}))
    result = run(aunload_model("m"))
    assert result.success is True
    assert fake.calls == [("http://127.0.0.0:8080/models/unload", {"model": "m"})]


def test_aunload_model_refuses_when_busy(monkeypatch):
    import llama_server_tool.unload as unload_module

    busy = [Slot(id=0, is_processing=False), Slot(id=1, is_processing=True)]

    async def fake_aget_slots(*args, **kwargs):
        return SlotsReport(slots=busy)

    monkeypatch.setattr(unload_module, "aget_slots", fake_aget_slots)
    fake = async_client(monkeypatch, response=json_response({"success": True}))
    result = run(aunload_model("m"))
    assert result.busy_slots == 1
    assert fake.calls == []  # refused before the POST


def test_aload_model(monkeypatch):
    fake = async_client(monkeypatch, response=json_response({"success": True}))
    result = run(aload_model("m"))
    assert result.success is True
    assert result.model == "m"
    assert fake.calls == [("http://127.0.0.0:8080/models/load", {"model": "m"})]
    assert fake.client_timeout.read == 300.0  # long default: the server may block on an LRU unload
    run(aload_model("m", timeout=60))
    assert fake.client_timeout.read == 60.0


def test_async_sync_parity(monkeypatch):
    """Given the same canned bodies, async and sync return equal models."""
    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response({"status": "ok"})))
    async_client(monkeypatch, response=json_response({"status": "ok"}))
    assert run(aget_health()) == check_health()

    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(MODELS_BODY)))
    async_client(monkeypatch, response=json_response(MODELS_BODY))
    assert run(aget_models()) == get_models()

    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(PROPS_BODY)))
    async_client(monkeypatch, response=json_response(PROPS_BODY))
    assert run(aget_props()) == get_props()

    monkeypatch.setattr(httpx, "get", FakeGet(response=text_response(SAMPLE_TEXT)))
    async_client(monkeypatch, response=text_response(SAMPLE_TEXT))
    assert run(aget_metrics()) == get_metrics()

    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(SLOTS_BODY)))
    async_client(monkeypatch, response=json_response(SLOTS_BODY))
    assert run(aget_slots()) == get_slots()

    # unload: both paths see the 400 slots check (not running) and the 400 POST error body
    import llama_server_tool.unload as unload_module

    not_loaded = {"error": {"code": 400, "message": "model is not loaded", "type": "invalid_request_error"}}
    not_running = {"error": {"code": 400, "message": "model is not running", "type": "invalid_request_error"}}

    async def fake_aget_slots(*args, **kwargs):
        return SlotsReport.model_validate(not_loaded)

    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(not_loaded, status_code=400)))
    monkeypatch.setattr(httpx, "post", FakeGet(response=json_response(not_running, status_code=400)))
    monkeypatch.setattr(unload_module, "aget_slots", fake_aget_slots)
    async_client(monkeypatch, response=json_response(not_running, status_code=400))
    assert run(aunload_model("m")) == unload_model("m")

    # load: both paths get the 404 not-found body
    not_found = {"error": {"code": 404, "message": "model is not found", "type": "not_found_error"}}
    monkeypatch.setattr(httpx, "post", FakeGet(response=json_response(not_found, status_code=404)))
    async_client(monkeypatch, response=json_response(not_found, status_code=404))
    assert run(aload_model("m")) == load_model("m")


def test_model_dump_json_for_tracing(monkeypatch):
    """The tracing injection path: async result serializes to JSON."""
    async_client(monkeypatch, response=json_response(PROPS_BODY))
    result = run(aget_props())
    payload = result.model_dump(mode="json")
    assert payload["model_path"] == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    assert result.model_dump_json().startswith("{")
