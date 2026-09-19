# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the models command (CLI) and the ModelList/ModelInfo models."""

import json
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from helpers import FakeGet, json_response
from llama_server_tool.__main__ import _complete_modalities, app
from llama_server_tool.models import ModelInfo, ModelList, format_bytes, format_params

runner = CliRunner()

LONG_ID = "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
VISION_ID = "Vision-2B.gguf"

SAMPLE_BODY = {
    "object": "list",
    "data": [
        {
            "id": LONG_ID,
            "object": "model",
            "created": 1735142223,
            "owned_by": "llamacpp",
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "status": {"value": "loaded", "args": []},
            "meta": {
                "vocab_type": True,
                "n_vocab": 128256,
                "n_ctx_train": 131072,
                "n_embd": 4096,
                "n_params": 8030261312,
                "size": 4912898304,
                "ftype": "Q4_K - Medium",
                "n_ctx": 4096,
            },
        },
        {
            "id": VISION_ID,
            "object": "model",
            "created": 1735142223,
            "owned_by": "llamacpp",
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
            "status": {"value": "unloaded", "args": []},
            "meta": None,
        },
    ],
}


def run_models(monkeypatch, fake, *args):
    monkeypatch.setattr(httpx, "get", fake)
    return runner.invoke(app, ["models", *args])


def test_models_ok(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 0
    assert result.output == f'"{LONG_ID}"\n"{VISION_ID}"\n'


def test_models_meta_null_still_lists_id(monkeypatch):
    body = {**SAMPLE_BODY, "data": [{**SAMPLE_BODY["data"][0], "meta": None}]}
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake)
    assert result.exit_code == 0
    assert result.output == f'"{LONG_ID}"\n'


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
    run_models(monkeypatch, fake, LONG_ID, "--server", "http://127.0.0.1:9999")
    assert fake.urls == ["http://127.0.0.1:9999/v1/models"]


def test_models_positional_exact_match(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, LONG_ID)
    assert result.exit_code == 0
    assert result.output == f'"{LONG_ID}"\n'


def test_models_positional_no_match(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "nosuchmodel")
    assert result.exit_code == 1
    assert "models: no model with id 'nosuchmodel'" in result.stderr


def test_models_positional_filtered_out(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, VISION_ID, "--loaded")
    assert result.exit_code == 1
    assert "models: no model with id 'Vision-2B.gguf'" in result.stderr


def test_models_cli_loaded(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--loaded")
    assert result.exit_code == 0
    assert result.output == f'"{LONG_ID}"\n'


def test_models_cli_loaded_empty(monkeypatch):
    body = {**SAMPLE_BODY, "data": [{**SAMPLE_BODY["data"][1], "status": {"value": "unloaded", "args": []}}]}
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake, "--loaded")
    assert result.exit_code == 0
    assert result.output == ""


def test_models_cli_reload(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--reload")
    assert result.exit_code == 0
    assert fake.params == {"reload": "1"}
    assert result.output == f'"{LONG_ID}"\n"{VISION_ID}"\n'


def test_models_cli_reload_with_filters(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--reload", "--loaded")
    assert result.exit_code == 0
    assert fake.params == {"reload": "1"}
    assert result.output == f'"{LONG_ID}"\n'


def test_models_cli_json_reload(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--json", "--reload")
    assert result.exit_code == 0
    assert fake.params == {"reload": "1"}
    assert json.loads(result.output)["object"] == "list"


def test_models_cli_input_modalities(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--input_modalities", "text,image")
    assert result.exit_code == 0
    assert result.output == f'"{VISION_ID}"\n'
    result = run_models(monkeypatch, fake, "--input_modalities", "text", "--input_modalities", "image")
    assert result.output == f'"{VISION_ID}"\n'  # AND: only the model with both matches


def test_models_cli_output_modalities(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--output_modalities", "text")
    assert result.exit_code == 0
    assert result.output == f'"{LONG_ID}"\n"{VISION_ID}"\n'
    result = run_models(monkeypatch, fake, "--output_modalities", "image")
    assert result.exit_code == 0
    assert result.output == ""


def test_models_cli_show_modalities(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--show-modalities")
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert lines[0].split() == ["id", "input", "output"]
    assert lines[1].split() == [f'"{LONG_ID}"', "text", "text"]
    assert lines[2].split() == [f'"{VISION_ID}"', "text,image", "text"]


def test_models_cli_show_meta(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--show-meta")
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert lines[0].split() == ["id", "n_params", "n_ctx_train", "n_embd", "n_vocab", "size", "vocab_type"]
    assert lines[1].split() == [f'"{LONG_ID}"', "8.03B", "131072", "4096", "128256", "4.91GB", "true"]
    assert len(lines) == 2  # --show-meta implies --loaded: the unloaded model is gone


def test_models_cli_meta_fields_implies_show_meta(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--meta-fields", "ftype,n_ctx")
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert lines[0].split() == ["id", "ftype", "n_ctx"]
    assert lines[1] == f'"{LONG_ID}" Q4_K - Medium 4096'


def test_models_cli_meta_fields_unknown(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--meta-fields", "bogus")
    assert result.exit_code == 1
    assert "models: unknown meta field(s) bogus" in result.stderr
    assert "available:" in result.stderr


def test_models_cli_json_conflict(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--json", "--loaded")
    assert result.exit_code == 1
    assert "models: --json cannot be combined with --loaded" in result.stderr
    result = run_models(monkeypatch, fake, "--json", "--loaded", "--show-meta")
    assert result.exit_code == 1
    assert "models: --json cannot be combined with --loaded, --show-meta" in result.stderr
    assert fake.urls == []  # rejected before any request


def test_model_list_match():
    ml = ModelList.model_validate(SAMPLE_BODY)
    assert [m.id for m in ml.match(VISION_ID).data] == [VISION_ID]
    assert ml.match("missing.gguf").data == []
    assert ml.match("nosuchmodel").data == []


def test_model_list_select_loaded():
    ml = ModelList.model_validate(SAMPLE_BODY)
    assert [m.id for m in ml.select(loaded=True).data] == [LONG_ID]


def test_model_list_select_modalities():
    ml = ModelList.model_validate(SAMPLE_BODY)
    assert [m.id for m in ml.select(input_modalities=["text"]).data] == [LONG_ID, VISION_ID]
    assert [m.id for m in ml.select(input_modalities=["text", "image"]).data] == [VISION_ID]
    assert ml.select(input_modalities=["image", "audio"]).data == []
    assert [m.id for m in ml.select(output_modalities=["text"]).data] == [LONG_ID, VISION_ID]
    assert ml.select(loaded=True, input_modalities=["text", "image"]).data == []


def test_model_list_select_missing_architecture():
    body = {
        "object": "list",
        "data": [
            {"id": "no-arch.gguf", "created": 1, "owned_by": "x"},
            SAMPLE_BODY["data"][1],
        ],
    }
    ml = ModelList.model_validate(body)
    assert [m.id for m in ml.select().data] == ["no-arch.gguf", VISION_ID]  # unfiltered: kept
    assert [m.id for m in ml.select(input_modalities=["text"]).data] == [VISION_ID]  # filtered: excluded


def test_render_default_quoted_ids():
    assert ModelList.model_validate(SAMPLE_BODY).render() == f'"{LONG_ID}"\n"{VISION_ID}"'


def test_render_empty():
    assert ModelList(data=[]).render() == ""
    assert ModelList(data=[]).render(show_meta=True) == ""


def test_render_error_unchanged():
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    assert ModelList.model_validate(body).render() == "models: Loading model"


def test_render_show_modalities_exact():
    body = {
        "object": "list",
        "data": [
            {"id": "a", "created": 1, "owned_by": "x", "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}},
            {"id": "bb", "created": 1, "owned_by": "x"},
        ],
    }
    expected = "\n".join(
        [
            "id   input      output",
            '"a"  text,image text',
            '"bb"',
        ]
    )
    assert ModelList.model_validate(body).render(show_modalities=True) == expected


def test_render_show_meta_exact():
    body = {
        "object": "list",
        "data": [
            {"id": "m", "created": 1, "owned_by": "x", "status": {"value": "loaded", "args": []}, "meta": {"n_params": 8030261312}},
        ],
    }
    expected = "id  n_params\n\"m\" 8.03B"
    assert ModelList.model_validate(body).render(show_meta=True, meta_fields=["n_params"]) == expected


def test_render_show_meta_matches_user_sample():
    body = {
        "object": "list",
        "data": [
            {
                "id": "Qwen3.8-27B",
                "created": 1,
                "owned_by": "llamacpp",
                "status": {"value": "loaded", "args": []},
                "meta": {
                    "vocab_type": True,
                    "n_vocab": 248320,
                    "n_ctx_train": 262144,
                    "n_embd": 5120,
                    "n_params": 27320697856,
                    "size": 17548181504,
                    "ftype": "Q4_K - Medium",
                    "n_ctx": 262144,
                },
            },
        ],
    }
    rendered = ModelList.model_validate(body).select(loaded=True).render(show_meta=True)
    lines = rendered.splitlines()
    assert lines[0].split() == ["id", "n_params", "n_ctx_train", "n_embd", "n_vocab", "size", "vocab_type"]
    assert lines[1].split() == ['"Qwen3.8-27B"', "27.32B", "262144", "5120", "248320", "17.55GB", "true"]


def test_render_meta_fields_order_and_blank_cells():
    body = {
        "object": "list",
        "data": [
            {"id": "a", "created": 1, "owned_by": "x", "meta": {"ftype": "Q4_K - Medium"}},
            {"id": "b", "created": 1, "owned_by": "x", "meta": {}},
        ],
    }
    expected = "\n".join(
        [
            "id  ftype",
            '"a" Q4_K - Medium',
            '"b"',  # field absent on this model: blank cell
        ]
    )
    assert ModelList.model_validate(body).render(show_meta=True, meta_fields=["ftype"]) == expected


def test_render_meta_default_lenient_without_meta():
    body = {"object": "list", "data": [{"id": "loading", "created": 1, "owned_by": "x", "meta": None}]}
    rendered = ModelList.model_validate(body).render(show_meta=True)  # default set, no strict check
    assert rendered.splitlines()[1].split() == ['"loading"']


def test_render_meta_fields_unknown_raises():
    ml = ModelList.model_validate(SAMPLE_BODY)
    with pytest.raises(ValueError, match="unknown meta field\\(s\\) bogus"):
        ml.render(show_meta=True, meta_fields=["bogus"])


def test_model_info_parses_meta_and_architecture():
    info = ModelInfo.model_validate(SAMPLE_BODY["data"][0])
    assert info.meta is not None
    assert info.meta["vocab_type"] is True  # bool preserved, not coerced to int
    assert info.meta["ftype"] == "Q4_K - Medium"
    assert info.meta["n_ctx"] == 4096
    assert info.architecture is not None
    assert info.architecture.input_modalities == ["text"]
    assert info.status is not None and info.status.value == "loaded"


def test_model_info_minimal():
    info = ModelInfo.model_validate({"id": "m.gguf", "created": 1, "owned_by": "llamacpp"})
    assert info.meta is None
    assert info.architecture is None
    assert info.status is None


def test_models_json_prints_raw_body(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, "--json")
    assert result.exit_code == 0
    assert "models:" not in result.output
    assert json.loads(result.output)["data"][0]["id"] == LONG_ID


def test_models_json_model_filter(monkeypatch):
    fake = FakeGet(response=json_response(SAMPLE_BODY))
    result = run_models(monkeypatch, fake, LONG_ID, "--json")
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["object"] == "list"
    assert [m["id"] for m in parsed["data"]] == [LONG_ID]


def test_models_json_model_filter_preserves_unknown_fields(monkeypatch):
    entry = {**SAMPLE_BODY["data"][1], "router_url": "http://x:1"}
    body = {"object": "list", "data": [SAMPLE_BODY["data"][0], entry]}
    fake = FakeGet(response=json_response(body))
    result = run_models(monkeypatch, fake, VISION_ID, "--json")
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


def test_format_params():
    assert format_params(8030261312) == "8.03B"
    assert format_params(750000000) == "750.00M"
    assert format_params(512) == "512"
    assert format_params(27320697856) == "27.32B"


def test_format_bytes():
    assert format_bytes(4912898304) == "4.91GB"
    assert format_bytes(1500) == "1.50KB"
    assert format_bytes(512) == "512B"
    assert format_bytes(17548181504) == "17.55GB"


def test_complete_modalities_union(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(SAMPLE_BODY)))
    assert _complete_modalities(SimpleNamespace(params={}), "") == ["image", "text"]


def test_complete_modalities_server_down(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeGet(error=httpx.ConnectError("nope")))
    assert _complete_modalities(SimpleNamespace(params={}), "") == ["audio", "image", "text", "video"]


def test_complete_modalities_prefix(monkeypatch):
    monkeypatch.setattr(httpx, "get", FakeGet(response=json_response(SAMPLE_BODY)))
    assert _complete_modalities(SimpleNamespace(params={}), "im") == ["image"]
    assert _complete_modalities(SimpleNamespace(params={}), "zz") == []
