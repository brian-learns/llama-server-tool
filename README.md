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
