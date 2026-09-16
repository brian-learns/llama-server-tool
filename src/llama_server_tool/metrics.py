"""
### GET `/metrics`: Prometheus compatible metrics exporter

This endpoint is only accessible if `--metrics` is set.

In *router mode* the query param `?model={model_id}` has to be set. This endpoint will respond with status code 400 `model name is missing from the request` if not set.

#### Available metrics

| Metric | Type | Description |
| ------ | ---------------------- | ----------- |
| `llamacpp:prompt_tokens_total` | Counter | Number of prompt tokens processed. |
| `llamacpp:prompt_seconds_total` | Counter | Prompt process time in seconds. |
| `llamacpp:prompt_tokens_seconds` | Gauge | Average prompt throughput in tokens/s. |
| `llamacpp:tokens_predicted_total` | Counter | Number of generation tokens processed. |
| `llamacpp:tokens_predicted_seconds_total` | Counter | Predict process time in seconds. |
| `llamacpp:predicted_tokens_seconds` | Gauge | Average generation throughput in tokens/s. |
| `llamacpp:requests_processing` | Gauge | Number of requests processing. |
| `llamacpp:requests_deferred` | Gauge | Number of requests deferred. |
| `llamacpp:n_tokens_max` | Counter | High watermark of the context size observed. |
| `llamacpp:n_decode_total` | Counter | Total Number of llama_decode() calls. |
| `llamacpp:n_busy_slots_per_decode` | Gauge | Average number of busy slots per llama_decode() call. |
| `llamacpp:spec_decode_num_draft_tokens_total` | Counter | Total draft tokens generated (0 when spec-decode is off). |
| `llamacpp:spec_decode_num_accepted_tokens_total` | Counter | Total draft tokens accepted by the target model (0 when spec-decode is off). |
| `llamacpp:spec_decode_num_drafts_total` | Counter | Total speculative decoding verification steps (0 when spec-decode is off). |
| `llamacpp:spec_decode_num_accepted_tokens_per_pos_total` | Counter | Accepted tokens per draft position (labeled `position="N"`; absent when spec-decode is off or before the first completed speculative request). |

"""

from prometheus_client.parser import text_string_to_metric_families
from pydantic import BaseModel

from .server import ApiError, format_value


class MetricSample(BaseModel):
    """A single sample of a metric family, with its labels and value."""

    labels: dict[str, str] = {}
    value: float


class MetricFamilyEntry(BaseModel):
    """One metric family (name, type, help text, samples) from the /metrics text."""

    name: str
    type: str
    help: str | None = None
    samples: list[MetricSample] = []

    def render(self) -> str:
        """Format the family section for output."""
        lines = [f"  {self.name} ({self.type})"]
        if self.help:
            lines.append(f"    {self.help}")
        for sample in self.samples:
            labels = "".join(f'[{k}="{v}"]' for k, v in sample.labels.items())
            value = format_value(sample.value)
            lines.append(f"      {labels}{value}" if not labels else f"      {labels} {value}")
        return "\n".join(lines)


class MetricsReport(BaseModel):
    """Parsed /metrics content (or an API error body), rendered by pydantic."""

    families: list[MetricFamilyEntry] = []
    error: ApiError | None = None

    def render(self) -> str:
        """Format the metrics report; families keep the server's order."""
        if self.error is not None:
            return f"metrics: {self.error.message}"
        return "\n".join(["metrics:", *(family.render() for family in self.families)])


def parse_exposition(text: str) -> list[MetricFamilyEntry]:
    """Parse Prometheus exposition text into MetricFamilyEntry models."""
    entries = []
    for family in text_string_to_metric_families(text):
        # The parser strips the counter "_total" suffix from family names (OpenMetrics
        # convention); sample names keep it, so prefer those to match the documented
        # llamacpp:* metric names.
        name = family.samples[0].name if family.samples else family.name
        entries.append(
            MetricFamilyEntry(
                name=name,
                type=family.type.lower(),
                help=family.documentation or None,
                samples=[MetricSample(labels=dict(sample.labels), value=sample.value) for sample in family.samples],
            )
        )
    return entries
