# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the metrics command (CLI) and the MetricsReport model."""

import httpx
from typer.testing import CliRunner

from helpers import FakeGet, json_response, text_response
from llama_server_tool.__main__ import app
from llama_server_tool.metrics import MetricFamilyEntry, MetricSample, MetricsReport, parse_exposition
from llama_server_tool.server import format_value

runner = CliRunner()

SAMPLE_TEXT = """\
# HELP llamacpp:predicted_tokens_seconds Average generation throughput in tokens/s.
# TYPE llamacpp:predicted_tokens_seconds gauge
llamacpp:predicted_tokens_seconds{model="Ornith-1.0-9B"} 12.5
# HELP llamacpp:prompt_tokens_total Number of prompt tokens processed.
# TYPE llamacpp:prompt_tokens_total counter
llamacpp:prompt_tokens_total 12345
# HELP llamacpp:spec_decode_num_accepted_tokens_per_pos_total Accepted tokens per draft position.
# TYPE llamacpp:spec_decode_num_accepted_tokens_per_pos_total counter
llamacpp:spec_decode_num_accepted_tokens_per_pos_total{position="0"} 123
llamacpp:spec_decode_num_accepted_tokens_per_pos_total{position="1"} 98
"""


def run_metrics(monkeypatch, fake, *args):
    monkeypatch.setattr(httpx, "get", fake)
    return runner.invoke(app, ["metrics", *args])


def test_metrics_ok(monkeypatch):
    fake = FakeGet(response=text_response(SAMPLE_TEXT))
    result = run_metrics(monkeypatch, fake)
    assert result.exit_code == 0
    assert "  llamacpp:predicted_tokens_seconds (gauge)" in result.output
    assert "    Average generation throughput in tokens/s." in result.output
    assert '      [model="Ornith-1.0-9B"] 12.5' in result.output
    assert "      12345.0" in result.output
    assert '      [position="0"] 123.0' in result.output
    assert '      [position="1"] 98.0' in result.output


def test_metrics_model_param(monkeypatch):
    fake = FakeGet(response=text_response(SAMPLE_TEXT))
    run_metrics(monkeypatch, fake, "foo")
    assert fake.urls == ["http://127.0.0.0:8080/metrics"]
    assert fake.params == {"model": "foo"}


def test_metrics_has_no_json_option():
    result = runner.invoke(app, ["metrics", "--help"])
    assert result.exit_code == 0
    assert "--json" not in result.output


def test_metrics_no_model_no_params(monkeypatch):
    fake = FakeGet(response=text_response(SAMPLE_TEXT))
    run_metrics(monkeypatch, fake)
    assert fake.params is None


def test_metrics_501_metrics_disabled(monkeypatch):
    body = {
        "error": {
            "code": 501,
            "message": "This server does not support metrics endpoint. Start it with `--metrics`",
            "type": "not_supported_error",
        }
    }
    fake = FakeGet(response=json_response(body, status_code=501))
    result = run_metrics(monkeypatch, fake)
    assert result.exit_code == 1
    assert "metrics: This server does not support metrics endpoint. Start it with `--metrics`" in result.output


def test_metrics_400_plain_text(monkeypatch):
    fake = FakeGet(response=text_response("model name is missing from the request", status_code=400))
    result = run_metrics(monkeypatch, fake)
    assert result.exit_code == 1
    assert "metrics: HTTP 400: model name is missing from the request" in result.stderr


def test_metrics_connection_error(monkeypatch):
    fake = FakeGet(error=httpx.ConnectError("connection refused"))
    result = run_metrics(monkeypatch, fake)
    assert result.exit_code == 1
    assert "metrics: connection refused" in result.stderr


def test_metrics_unparseable_text(monkeypatch):
    fake = FakeGet(response=text_response("this is not exposition text"))
    result = run_metrics(monkeypatch, fake)
    assert result.exit_code == 1
    assert "failed to parse exposition text" in result.stderr


def test_report_renders_families_in_order():
    expected = """\
metrics:
  llamacpp:predicted_tokens_seconds (gauge)
    Average generation throughput in tokens/s.
      [model="Ornith-1.0-9B"] 12.5
  llamacpp:prompt_tokens_total (counter)
    Number of prompt tokens processed.
      12345.0
  llamacpp:spec_decode_num_accepted_tokens_per_pos_total (counter)
    Accepted tokens per draft position.
      [position="0"] 123.0
      [position="1"] 98.0"""
    assert MetricsReport(families=parse_exposition(SAMPLE_TEXT)).render() == expected


def test_family_without_help_renders_without_description():
    family = MetricFamilyEntry(
        name="x:y",
        type="gauge",
        help=None,
        samples=[MetricSample(labels={}, value=1.0)],
    )
    assert family.render() == "  x:y (gauge)\n      1.0"


def test_report_renders_error():
    body = {"error": {"code": 501, "message": "no metrics", "type": "not_supported_error"}}
    assert MetricsReport.model_validate(body).render() == "metrics: no metrics"


def test_value_rounding():
    assert format_value(12.500000001) == "12.5"
    assert format_value(12345.0) == "12345.0"
