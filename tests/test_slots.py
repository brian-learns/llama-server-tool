# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the slots command (CLI) and the SlotsReport/Slot models."""

import httpx
import pytest
from typer.testing import CliRunner

from helpers import FakeGet, json_response
from llama_server_tool import get_slots
from llama_server_tool.__main__ import app
from llama_server_tool.server import ApiError, ServerError
from llama_server_tool.slots import Slot, SlotsReport

runner = CliRunner()

SAMPLE_BODY = [
    {
        "id": 0,
        "id_task": 135,
        "n_ctx": 65536,
        "speculative": False,
        "is_processing": True,
        "params": {"temperature": 0.800000011920929, "top_k": 40, "samplers": ["top_k"]},
        "next_token": {"has_next_token": True, "has_new_line": True, "n_remain": -1, "n_decoded": 136},
    },
    {
        "id": 1,
        "id_task": 0,
        "n_ctx": 65536,
        "speculative": False,
        "is_processing": False,
    },
]


def run_slots(monkeypatch, fake, *args):
    monkeypatch.setattr(httpx, "get", fake)
    return runner.invoke(app, ["slots", *args])


def test_slots_ok(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_slots(monkeypatch, fake, "Ornith-1.0-9B")
    assert result.exit_code == 0
    assert "slots (Ornith-1.0-9B):" in result.output
    assert "  slot 0:" in result.output
    assert "is_processing: true" in result.output
    assert "n_decoded:     136" in result.output
    assert "  slot 1:" in result.output
    assert "is_processing: false" in result.output


def test_slots_model_param(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_slots(monkeypatch, fake, "foo")
    assert fake.urls == ["http://127.0.0.0:8080/slots"]
    assert fake.params == {"model": "foo"}
    run_slots(monkeypatch, fake)
    assert fake.params is None


def test_slots_400_missing_model(monkeypatch):
    body = {"error": {"code": 400, "message": "model name is missing from the request", "type": "invalid_request_error"}}
    fake = FakeGet(response=json_response(body, status_code=400))
    result = run_slots(monkeypatch, fake)
    assert result.exit_code == 1
    assert "slots: model name is missing from the request" in result.output


def test_slots_connection_error(monkeypatch):
    fake = FakeGet(error=httpx.ConnectError("connection refused"))
    result = run_slots(monkeypatch, fake)
    assert result.exit_code == 1
    assert "slots: connection refused" in result.stderr


def test_slots_empty_list(monkeypatch):
    fake = FakeGet(response=json_response([]))
    result = run_slots(monkeypatch, fake)
    assert result.exit_code == 0
    assert result.output.strip() == "slots:"


def test_slots_non_list_body(monkeypatch):
    fake = FakeGet(response=json_response({"not": "a list"}))
    result = run_slots(monkeypatch, fake)
    assert result.exit_code == 1
    assert "failed to parse slots response" in result.stderr


def test_report_renders_fixture():
    expected = """\
slots (Ornith-1.0-9B):
  slot 0:
    is_processing: true
    n_ctx:         65536
    speculative:   false
    id_task:       135
    n_decoded:     136
    n_remain:      -1
  slot 1:
    is_processing: false
    n_ctx:         65536
    speculative:   false
    id_task:       0"""
    assert SlotsReport(model_name="Ornith-1.0-9B", slots=[Slot.model_validate(s) for s in SAMPLE_BODY]).render() == expected


def test_slot_all_optional_absent():
    assert Slot().render() == "  slot None:"


def test_slot_params_parsed_not_rendered():
    slot = Slot.model_validate(SAMPLE_BODY[0])
    assert slot.params is not None
    assert slot.params.temperature == 0.800000011920929
    assert "temperature" not in slot.render()


def test_slot_next_token_as_list():
    slot = Slot.model_validate(
        {"id": 3, "is_processing": False, "next_token": [{"has_next_token": False, "n_decoded": 7}]}
    )
    rendered = slot.render()
    assert "n_decoded:     7" in rendered


def test_get_slots_503_returns_error_model(monkeypatch):
    body = {"error": {"code": 503, "message": "no available slots", "type": "unavailable_error"}}
    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(body, status_code=503)))
    result = get_slots()
    assert isinstance(result.error, ApiError)
    assert result.error.message == "no available slots"


def test_get_slots_non_json_error_raises(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", FakeGet(response=httpx.Response(500, text="boom", request=httpx.Request("GET", "x")))
    )
    with pytest.raises(ServerError, match="HTTP 500: boom"):
        get_slots()
