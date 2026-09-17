# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the models command (CLI) and the ModelList/ModelInfo models."""

import json

import httpx
from typer.testing import CliRunner

from helpers import FakeGet, json_response
from llama_server_tool.__main__ import app
from llama_server_tool.models import (
    ModelInfo,
    ModelList,
    ModelMeta,
    format_bytes,
    format_created,
    format_params,
)

runner = CliRunner()

SAMPLE_BODY = {
    "object": "list",
    "data": [
        {
            "id": "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
            "object": "model",
            "created": 1735142223,
            "owned_by": "llamacpp",
            "meta": {
                "vocab_type": 2,
                "n_vocab": 128256,
                "n_ctx_train": 131072,
                "n_embd": 4096,
                "n_params": 8030261312,
                "size": 4912898304,
            },
        }
    ],
}


def run_models(monkeypatch, fake, *args):
    monkeypatch.setattr(httpx, "get", fake)
    return runner.invoke(app, ["models", *args])


def test_models_ok(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 0
    assert "models:" in result.output
    assert "id:         ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf" in result.output
    assert "created:    2024-12-25 15:57:03 UTC" in result.output
    assert "owned_by:   llamacpp" in result.output
    assert "n_params:    8.03B" in result.output
    assert "size:        4.91 GB" in result.output


def test_models_meta_null(monkeypatch):
    body = {**SAMPLE_BODY, "data": [{**SAMPLE_BODY["data"][0], "meta": None}]}
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 0
    assert "meta: (null — model may still be loading)" in result.output


def test_models_503_error_body(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    fake = FakeGet(response=json_response(body, status_code=503))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 1
    assert "models: Loading model" in result.output


def test_models_connection_error(monkeypatch):
    fake = FakeGet(error=httpx.ConnectError("connection refused"))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 1
    assert "models: connection refused" in result.stderr


def test_models_malformed_json(monkeypatch):
    fake = FakeGet(response=httpx.Response(200, text="not json", request=httpx.Request("GET", "x")))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 1
    assert "invalid JSON from /v1/models" in result.stderr


def test_models_server_option(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    run_models(monkeypatch, fake, "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf", "--server", "http://127.0.0.1:9999")
    assert fake.urls == ["http://127.0.0.1:9999/v1/models"]


def test_models_positional_exact_match(monkeypatch):
    body = {
        "object": "list",
        "data": [SAMPLE_BODY["data"][0], {**SAMPLE_BODY["data"][0], "id": "other.gguf"}],
    }
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake, "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")
    assert result.exit_code == 0
    assert "id:         ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf" in result.output
    assert "other.gguf" not in result.output


def test_models_positional_no_match(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "nosuchmodel")
    assert result.exit_code == 1
    assert "models: no model with id 'nosuchmodel'" in result.stderr


def test_model_list_match():
    body = {
        "object": "list",
        "data": [SAMPLE_BODY["data"][0], {**SAMPLE_BODY["data"][0], "id": "other.gguf"}],
    }
    ml = ModelList.model_validate(body)
    assert [m.id for m in ml.match("other.gguf").data] == ["other.gguf"]
    assert ml.match("missing.gguf").data == []
    assert ml.match("OTHER.GGUF").data == []  # exact match is case-sensitive


def test_models_json_prints_raw_body(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--json")
    assert result.exit_code == 0
    assert "models:" not in result.output
    assert json.loads(result.output)["data"][0]["id"] == "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"


def test_models_json_model_filter(monkeypatch):
    body = {
        "object": "list",
        "data": [SAMPLE_BODY["data"][0], {**SAMPLE_BODY["data"][0], "id": "other.gguf"}],
    }
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake, "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf", "--json")
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["object"] == "list"
    assert [m["id"] for m in parsed["data"]] == ["../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"]


def test_models_json_model_filter_preserves_unknown_fields(monkeypatch):
    entry = {**SAMPLE_BODY["data"][0], "id": "other.gguf", "router_url": "http://x:1"}
    body = {"object": "list", "data": [SAMPLE_BODY["data"][0], entry]}
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake, "other.gguf", "--json")
    assert result.exit_code == 0
    assert json.loads(result.output)["data"][0]["router_url"] == "http://x:1"


def test_models_json_model_no_match(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "nosuchmodel", "--json")
    assert result.exit_code == 1
    assert "models: no model with id 'nosuchmodel'" in result.stderr


def test_models_json_model_503_prints_error_body(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    fake = FakeGet(response=json_response(body, status_code=503))
    result = run_models(monkeypatch, fake, "any", "--json")
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["message"] == "Loading model"


def test_models_json_503_prints_raw_body_and_exits_1(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    fake = FakeGet(response=json_response(body, status_code=503))
    result = run_models(monkeypatch, fake, "--json")
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["message"] == "Loading model"


def test_model_list_renders_full_report():
    expected = """\
models:
  id:         ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
  created:    2024-12-25 15:57:03 UTC
  owned_by:   llamacpp
  meta:
    n_params:    8.03B
    n_ctx_train: 131072
    n_embd:      4096
    n_vocab:     128256
    size:        4.91 GB
    vocab_type:  2"""
    assert ModelList.model_validate(SAMPLE_BODY).render() == expected


def test_model_info_renders_null_meta():
    info = ModelInfo(id="m.gguf", created=1735142223, owned_by="llamacpp", meta=None)
    assert info.render().endswith("meta: (null — model may still be loading)")


def test_model_list_renders_error():
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    assert ModelList.model_validate(body).render() == "models: Loading model"


def test_format_params():
    assert format_params(8030261312) == "8.03B"
    assert format_params(750000000) == "750.00M"
    assert format_params(512) == "512"


def test_format_bytes():
    assert format_bytes(4912898304) == "4.91 GB"
    assert format_bytes(1500) == "1.50 KB"
    assert format_bytes(512) == "512 B"


def test_format_created():
    assert format_created(1735142223) == "2024-12-25 15:57:03 UTC"


def test_model_meta_renders():
    meta = ModelMeta(
        vocab_type=2,
        n_vocab=128256,
        n_ctx_train=131072,
        n_embd=4096,
        n_params=8030261312,
        size=4912898304,
    )
    expected = """\
    n_params:    8.03B
    n_ctx_train: 131072
    n_embd:      4096
    n_vocab:     128256
    size:        4.91 GB
    vocab_type:  2"""
    assert meta.render() == expected
