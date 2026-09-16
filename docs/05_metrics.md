# Phase 4: `metrics`

Plan for the fourth and final command of the initial scope: `llama-server-tool metrics`.

## CLI

```
llama-server-tool metrics [--model ID]
```

- `--model` — passed as `?model=<id>` (required by the server in router mode; without
  it the endpoint answers 400 `model name is missing from the request`)
- `--server` / `LLAMA_SERVER_URL` / default as with the other commands
- The endpoint is only available if the server was started with `--metrics`

## Dependency

Add `prometheus_client` (official Prometheus client library; pure Python, no hard deps).
We use **only** its parser — `prometheus_client.parser.text_string_to_metric_families`
— to turn the raw exposition text into structured `MetricFamily` objects. No custom
parser, no `prometheus-api-client` (that's for querying a running Prometheus server
with PromQL — a possible later feature, out of scope).

## Shared change

`/metrics` returns plain text, not JSON, so `server.py` gains a lower-level helper:

- `fetch(base, path, params) -> tuple[int, str]` — raw text response; raises
  `ServerError` on connect/timeout (moves the httpx call out of `fetch_json`)
- `fetch_json(base, path, params)` — refactored to call `fetch` and parse JSON;
  behavior unchanged for `health`/`models`/`props`

## Code shape

- `metrics.py` — pydantic models own validation + rendering (per conventions),
  populated from the parser output:
  - `MetricSample`: `labels: dict[str, str]`, `value: float`
  - `MetricFamilyEntry`: `name: str`, `type: str` (`counter`/`gauge`/...),
    `help: str | None`, `samples: list[MetricSample]`
  - `MetricsReport`: `families: list[MetricFamilyEntry]`, `error: ApiError | None`
    (400 bodies from this server are plain text, not JSON — the 400 case is handled
    in the command, not the model)
  - Rendering is **generic**: one section per family, in the order the server emits
    them, so new/renamed upstream metrics keep working without code changes:

    ```
    metrics:
      llamacpp:predicted_tokens_seconds (gauge)
        Average generation throughput in tokens/s.
          [model="Qwen3.8-27B"] 12.5
      llamacpp:spec_decode_num_accepted_tokens_per_pos_total (counter)
        Accepted tokens per draft position.
          [position="0"] 123
          [position="1"] 98
    ```

  - values render via the same rounded style as `props` (`round(value, 4)`);
    labels render as `[k="v"]` (omitted when the sample has none); the `# HELP`
    line becomes the description line (omitted when absent)
- `__main__.py` — thin `metrics` command:
  - `params = {"model": model}` when `--model` given, else `None`
  - `status, text = fetch(base, "/metrics", params=params)`
  - `ServerError` → stderr + exit 1
  - non-200 with a JSON error body (e.g. `501 {"error": {"message": "This server
    does not support metrics endpoint. Start it with \`--metrics\`", ...}}` when
    `--metrics` is off) → `metrics: <message>` on stdout, exit 1 (same pattern as
    the other commands)
  - non-200 with a plain-text body (e.g. `400 model name is missing from the
    request` in router mode) → `metrics: HTTP <status>: <body>` on stderr, exit 1
  - 200: parse with `text_string_to_metric_families` (parse error → stderr + exit 1),
    build `MetricsReport`, `echo(render())`, exit 0

## Tests (`tests/test_metrics.py`)

CLI (via `CliRunner` + `FakeGet`; new `text_response` helper in `tests/helpers.py`):

1. `200` sample exposition text → exit 0, family sections + description + values
2. labeled sample renders `[k="v"]`; unlabeled renders bare value
3. `--model foo` → URL `/metrics` with `model=foo` param; no `--model` → no params
4. `501` JSON error body (metrics disabled) → exit 1, `metrics: <message>` on stdout
5. `400` plain-text body (router mode, missing model) → exit 1, body text on stderr
6. connection error → exit 1, stderr message
7. `200` with garbage (non-exposition) text → exit 1, stderr message

Model tests (direct):

8. `MetricsReport` render: multiple families, order preserved
9. family with no help line renders without the description line
10. value rounding: `12.500000001 → 12.5`, `12345.0 → 12345.0`

Fixture exposition text: small synthetic counter/gauge families (no real server data).

## Verification

- `make test`
- live (needs the server restarted with `--metrics`):
  `uv run llama-server-tool metrics --model Qwen3.8-27B` and the 400 path without
  `--model` in router mode. Metrics output is numbers-only — session-safe.

## Out of scope for this phase

- querying a Prometheus server (PromQL) via `prometheus-api-client`
- rate/throughput computation across samples (single snapshot only)
- `--json` raw output
