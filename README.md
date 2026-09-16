<!--
SPDX-License-Identifier: 0BSD
Copyright (c) 2026 llama_server_tool creators and contributors
-->

# llama-server-tool

A command line tool (and Python API) to administer a local
[llama-server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Each command wraps one server endpoint and prints a formatted report:

| Command | Endpoint | Shows |
| ------- | -------- | ----- |
| `health` | `GET /health` | whether the model is loaded and the server is ready |
| `models` | `GET /v1/models` | the registered models and their metadata |
| `props` | `GET /props` | server properties and default generation settings |
| `metrics` | `GET /metrics` | Prometheus metrics (throughput, token totals, busy slots) |

## Install

```sh
uv tool install llama-server-tool   # or: pip install llama-server-tool
```

## Usage

Running the tool with no command lists the available commands.

```
$ llama-server-tool
 ...
╭─ Commands ────────────────────────────────────────────────────────────────────╮
│ health   Check server health via GET /health.                                 │
│ models   Show the loaded model via GET /v1/models.                            │
│ props    Show server properties via GET /props.                               │
│ metrics  Show server metrics via GET /metrics (Prometheus format).            │
╰───────────────────────────────────────────────────────────────────────────────╯
```

### health

```
$ llama-server-tool health
health: ok
```

Exits non-zero while the model is still loading (503).

### models

```
$ llama-server-tool models
models:
  id:         Qwen3.8-27B
  created:    2026-09-16 22:00:23 UTC
  owned_by:   llamacpp
  meta:
    n_params:    27.32B
    n_ctx_train: 262144
    n_embd:      5120
    n_vocab:     248320
    size:        17.55 GB
    vocab_type:  1
```

### props

```
$ llama-server-tool props --model Qwen3.8-27B
props:
  model_path:          /home/.../Qwen3.8-27B-UD-Q4_K_XL.gguf
  total_slots:         4
  is_sleeping:         false
  modalities:          vision=true, video=true, audio=false
  build_info:          b10988-9f31776c3
  chat_template:       <hidden: 27159 chars>
  generation settings:
    n_ctx:         262144
    params:
      temperature:       0.85
      top_k:             20
      ...
```

- `--model <id>` queries one model. The default is `autoload=false`, so the
  query never makes the server load or pre-warm the model; pass `--autoload`
  to opt in.
- The chat template is raw Jinja2 and is intentionally not printed.

### metrics

Requires the server to be started with `--metrics`; in router mode a model id
is required.

```
$ llama-server-tool metrics --model Qwen3.8-27B
metrics:
  llamacpp:predicted_tokens_seconds (gauge)
    Average generation throughput in tokens/s
      12.5
  llamacpp:requests_processing (gauge)
    Number of requests processing
      0.0
  ...
```

## Server URL

All commands take `--server <url>`; without it, the `LLAMA_SERVER_URL`
environment variable is used, falling back to `http://127.0.0.0:8080`.

## Python API

The same operations are importable, returning validated pydantic models —
well-formed server errors come back with `.error` set, transport failures
raise `ServerError`:

```python
from llama_server_tool import check_health, get_props, ServerError

try:
    health = check_health()
except ServerError as err:
    raise SystemExit(f"server unavailable: {err}")

if health.error is not None:
    raise SystemExit(health.error.message)

props = get_props(model="Qwen3.8-27B")
print(props.model_path)          # field access for automation
print(props.render())            # or the same report the CLI prints
```

Available: `check_health()`, `get_models()`, `get_props(model=...,
autoload=...)`, `get_metrics(model=...)`, plus the models
(`Health`, `ModelList`, `Props`, `MetricsReport`) and
`ApiError` / `ServerError`.

## Development

```sh
make            # list targets
make test       # static pipeline (ruff, bandit, vulture, refurb, ty, ...) + pytest
```

Tests need no running server (HTTP is mocked). Planning documents for each
phase live in `docs/`.

## License

[0BSD](LICENSE)
