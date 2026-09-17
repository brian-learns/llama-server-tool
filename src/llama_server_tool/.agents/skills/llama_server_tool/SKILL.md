---
name: llama_server_tool
description: Query and report on a local llama.cpp llama-server — health, models, server properties, Prometheus metrics — via CLI or Python API. Use when asked to check llama-server health, list or inspect models, read server properties or generation settings, or get token/throughput metrics.
---

<!--
SPDX-License-Identifier: 0BSD
Copyright (c) 2026 llama_server_tool creators and contributors
-->

# llama_server_tool

A CLI and Python API to administer a local llama.cpp `llama-server`. Each
command wraps one server endpoint and prints a formatted report.

```
$ llama-server-tool health
health: ok
```

Two invocation paths: `llama-server-tool ...` (when installed) and
`uv run python -m llama_server_tool ...` (from a checkout).
`llama-server-tool` with no command lists the available commands.

## Server URL

Every command takes `--server <url>`. Without it, the `LLAMA_SERVER_URL`
environment variable is used, falling back to `http://127.0.0.0:8080`.

## Raw JSON output

`health`, `models`, `props`, and `slots` take `--json` to print the
server's response body verbatim (the server's own JSON — fields the
formatted report omits are included). Exit 0 on 2xx, 1 otherwise, so error
bodies stay in the pipe:

```
$ llama-server-tool models --json | jq '.data[].id'
$ llama-server-tool models Qwen3.8-27B --json   # filtered to that exact id
```

`models MODEL --json` filters the JSON to the exact id (same envelope, so
the same `jq` expressions work). `metrics` has no `--json` (its report is
parsed from Prometheus exposition text). **`props --json` prints the full
`chat_template` (raw Jinja2).**

## Commands

### health — `GET /health`

```
$ llama-server-tool health
health: ok
```

Exit 0 when ready; exit 1 while the model is still loading (503) or the
server is unreachable.

### models — `GET /v1/models`

Lists the registered models with metadata (params, context, size). The
optional positional `MODEL` filters client-side to the entry with that exact
id (no match → exit 1).

```
$ llama-server-tool models
models:
  id:         Qwen3.8-27B
  created:    2026-09-16 22:00:23 UTC
  owned_by:   llamacpp
  meta:
    n_params:    27.32B
    n_ctx_train: 262144
    size:        17.55 GB
    ...
```

### props — `GET /props`

Server properties and default generation settings.

```
$ llama-server-tool props Qwen3.8-27B
props:
  model_path:          /home/.../Qwen3.8-27B-UD-Q4_K_XL.gguf
  total_slots:         4
  chat_template:       <hidden: 27159 chars>
  generation settings:
    n_ctx:         262144
    params:
      temperature:       0.85
      top_k:             20
      ...
```

- The positional `MODEL` queries one model. The default is `autoload=false`,
  so the query never makes the server load or pre-warm the model; pass
  `--autoload` to opt in.
- `--autoload` holds the request until the model is loaded, so it uses a
  5-minute read timeout by default; override with `--timeout <seconds>`
  (or `timeout=` in the API).
- The chat template is raw Jinja2 and is intentionally not printed.

### metrics — `GET /metrics`

Prometheus metrics (throughput, token totals, busy slots, spec-decode stats).

```
$ llama-server-tool metrics Qwen3.8-27B
metrics:
  llamacpp:predicted_tokens_seconds (gauge)
    Average generation throughput in tokens/s
      12.5
  llamacpp:requests_processing (gauge)
    Number of requests processing
      0.0
```

- The server must be started with `--metrics` (otherwise exit 1 with the
  server's 501 message).
- In router mode the positional `MODEL` is required (otherwise the server
  answers 400).

### slots — `GET /slots`

Per-slot busy state (which slots are processing, context size, tokens
decoded).

```
$ llama-server-tool slots Qwen3.8-27B
slots (Qwen3.8-27B):
  slot 0:
    is_processing: true
    n_ctx:         65536
    speculative:   false
    id_task:       135
    n_decoded:     136
```

In router mode the positional `MODEL` is required (otherwise the server
answers 400).

### status — board of loaded models

Opens with the router process itself (`llama-server` header; port from the
server URL, PID via a `/proc` cmdline scan — works across accounts), then
per loaded model: PID/port (port from the registry's `status.args`),
RSS/VSZ/VRAM, and one line per slot. Ends with a `free -h` + `nvidia-smi`
footer (`--no-system` omits it). Made for `watch -n 1 llama-server-tool
status`.

```
$ llama-server-tool status
=================================================================
llama-server (PID: 404576 | Port: 9931)
 -> Unified System RAM (RSS): 0.39 GB
 -> Virtual Memory Footprint: 15.36 GB
 -> Dedicated Blackwell VRAM: 0.17 GB
=================================================================

=================================================================
Qwen3.8-27B (PID: 342265 | Port: 48249)
 -> Unified System RAM (RSS): 21.71 GB
 -> Virtual Memory Footprint: 139.87 GB
 -> Dedicated Blackwell VRAM: 37.65 GB
 -> Slot [0]: Status = IDLE | Context Ingested = 0 tokens | Active Gen Tokens = 0 | n_ctx = 262144
 -> Slot [3]: Status = PROCESSING | Context Ingested = 4433 tokens | Active Gen Tokens = 0 | n_ctx = 262144
=================================================================
```

Only `loaded` models appear (the registry lists every loadable one; use
`models` for that). `status MODEL` focuses on one.

## Exit codes

`0` success; `1` server error, unhealthy state, or unreachable server
(transport errors go to stderr).

## Python API

The same operations are importable, returning validated pydantic models —
well-formed server errors come back with `.error` set, transport and parse
failures raise `ServerError`:

```python
from llama_server_tool import check_health, get_models, get_props, get_metrics, ServerError

try:
    health = check_health()
except ServerError as err:
    raise SystemExit(f"server unavailable: {err}")

if health.error is not None:
    raise SystemExit(health.error.message)

props = get_props(model="Qwen3.8-27B")
print(props.model_path)  # field access for automation
print(props.render())  # or the same report the CLI prints
```

`get_props(model=..., autoload=...)`, `get_metrics(model=...)` and
`get_slots(model=...)` mirror the CLI options; the models are `Health`,
`ModelList`, `Props`, `MetricsReport`, `SlotsReport`, with `ApiError` /
`ServerError` for error types. The package is typed (`py.typed`).

Every function has an async twin for asyncio code (`aget_health()`,
`aget_models()`, `aget_props(...)`, `aget_metrics()`, `aget_slots(...)`) with
identical behavior and return types:

```python
props = await llama_server_tool.aget_props(model="Qwen3.8-27B")
```
