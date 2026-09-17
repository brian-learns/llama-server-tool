# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the props command (CLI) and the Props model."""

import httpx
import pytest
from typer.testing import CliRunner

from helpers import FakeGet, json_response
from llama_server_tool.__main__ import app
from llama_server_tool.props import Props, get_props
from llama_server_tool.server import ServerError, format_value

runner = CliRunner()

TEMPLATE = "{% for m in messages %}{{ m.content }}{% endfor %}"

SAMPLE_BODY = {
    "default_generation_settings": {
        "id": 0,
        "n_ctx": 1024,
        "speculative": False,
        "is_processing": False,
        "params": {
            "n_predict": -1,
            "seed": 4294967295,
            "temperature": 0.800000011920929,
            "top_k": 40,
            "top_p": 0.949999988079071,
            "min_p": 0.05000000074505806,
            "repeat_penalty": 1.0,
            "ignore_eos": False,
            "stream": True,
            "samplers": ["dry", "top_k", "top_p", "temperature"],
            "stop": [],
        },
    },
    "total_slots": 1,
    "model_path": "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    "chat_template": TEMPLATE,
    "chat_template_caps": {},
    "modalities": {"vision": False},
    "is_sleeping": False,
    "build_info": "b6909-abcdef",
}


def run_props(monkeypatch, fake, *args):
    monkeypatch.setattr(httpx, "get", fake)
    return runner.invoke(app, ["props", *args])


def test_props_ok_hides_template(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_props(monkeypatch, fake)
    assert result.exit_code == 0
    assert "model_path:          ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf" in result.output
    assert f"chat_template:       <hidden: {len(TEMPLATE)} chars>" in result.output
    assert "temperature:       0.8" in result.output
    assert TEMPLATE not in result.output


def test_props_model_param_default_autoload_false(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_props(monkeypatch, fake, "foo")
    assert fake.urls == ["http://127.0.0.0:8080/props"]
    assert fake.params == {"model": "foo", "autoload": "false"}


def test_props_model_param_autoload_true(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_props(monkeypatch, fake, "foo", "--autoload")
    assert fake.params == {"model": "foo", "autoload": "true"}


def test_props_no_model_no_params(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_props(monkeypatch, fake)
    assert fake.urls == ["http://127.0.0.0:8080/props"]
    assert fake.params is None


def test_props_503_error_body(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    fake = FakeGet(response=json_response(body, status_code=503))
    result = run_props(monkeypatch, fake)
    assert result.exit_code == 1
    assert "props: Loading model" in result.output


def test_props_connection_error(monkeypatch):
    fake = FakeGet(error=httpx.ConnectError("connection refused"))
    result = run_props(monkeypatch, fake)
    assert result.exit_code == 1
    assert "props: connection refused" in result.stderr


def test_props_renders_full_report():
    expected = f"""\
props:
  model_path:          ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
  total_slots:         1
  is_sleeping:         false
  modalities:          vision=false
  build_info:          b6909-abcdef
  chat_template:       <hidden: {len(TEMPLATE)} chars>
  generation settings:
    id:            0
    n_ctx:         1024
    speculative:   false
    is_processing: false
        params:
          n_predict:         -1
          seed:              4294967295
          temperature:       0.8
          top_k:             40
          top_p:             0.95
          min_p:             0.05
          repeat_penalty:    1.0
          ignore_eos:        false
          stream:            true
          samplers:          dry, top_k, top_p, temperature"""
    assert Props.model_validate(SAMPLE_BODY).render() == expected


def test_props_empty_body_renders_without_crash():
    assert Props().render() == "props:"


def test_props_omits_absent_fields():
    body = Props(model_path="m.gguf")
    assert body.render() == "props:\n  model_path:          m.gguf"


def test_get_props_default_timeout(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    monkeypatch.setattr(httpx, "get", fake)
    get_props(model="x")
    assert fake.timeout.read == 5.0
    assert fake.timeout.connect == 5.0


def test_get_props_autoload_timeout(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    monkeypatch.setattr(httpx, "get", fake)
    get_props(model="x", autoload=True)
    assert fake.timeout.read == 300.0


def test_get_props_explicit_timeout_wins(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    monkeypatch.setattr(httpx, "get", fake)
    get_props(model="x", autoload=True, timeout=60)
    assert fake.timeout.read == 60.0


def test_props_cli_autoload_timeout(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_props(monkeypatch, fake, "x", "--autoload")
    assert fake.timeout.read == 300.0


def test_props_cli_timeout_override(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_props(monkeypatch, fake, "x", "--autoload", "--timeout", "60")
    assert fake.timeout.read == 60.0


def test_props_cli_timeout_without_autoload(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_props(monkeypatch, fake, "--timeout", "60")
    assert fake.timeout.read == 60.0


def test_fetch_timeout_message(monkeypatch):
    def timed_out_get(url, timeout=None, params=None):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx, "get", timed_out_get)
    with pytest.raises(ServerError, match="timed out after 300.0s"):
        get_props(model="x", autoload=True)
    with pytest.raises(ServerError, match="timed out after 5.0s"):
        get_props()


def test_format_value_rounds_floats():
    assert format_value(0.800000011920929) == "0.8"
    assert format_value(1.0) == "1.0"
    assert format_value(True) == "true"
    assert format_value(False) == "false"
    assert format_value(["a", "b"]) == "a, b"
    assert format_value(42) == "42"


def test_template_content_never_rendered():
    secret = "SECRETJINJATEMP"
    body = Props(chat_template=secret * 100)
    rendered = body.render()
    assert secret not in rendered
    assert f"<hidden: {len(secret) * 100} chars>" in rendered
