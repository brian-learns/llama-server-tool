# llama-server-tool

A command line tool (and Python API) to administer a local
[llama-server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

Each command wraps one server endpoint and prints a formatted report:

| Command | Endpoint | Shows |
| ------- | -------- | ----- |
| `health` | `GET /health` | whether the model is loaded and the server is ready |
| `models` | `GET /v1/models` | the model registry as quoted ids; `--reload` refreshes it from the models dir (mutating); filters (`--loaded`, `--input_modalities`, `--output_modalities`) and table columns (`--show-modalities`, `--show-meta`) |
| `props` | `GET /props` | server properties and default generation settings |
| `metrics` | `GET /metrics` | Prometheus metrics (throughput, token totals, busy slots) |
| `slots` | `GET /slots` | per-slot busy state (processing, context, tokens decoded) |
| `load` | `POST /models/load` | loads a model (router mode); fire-and-launch (the instance is spawned, state loading) |
| `unload` | `POST /models/unload` | unloads a model (router mode); refuses while a slot is processing unless `--force` |
| `status` | `GET /v1/models` + `GET /slots` + OS | board of loaded models: server header (router memory), per-model memory (RSS/VSZ/VRAM), slot state, and a `free`/`nvidia-smi` footer (omit with `--no-system`) |

Commands that query a specific model take it as a positional argument
(`props MODEL`, `metrics MODEL`, `slots MODEL`). `models MODEL` filters the
registry client-side to the entry with that exact id.

`health`, `models`, `props`, and `slots` take `--json` to print the
server's raw JSON response body instead of the formatted report — for
scripting, e.g. `llama-server-tool models --json | jq '.data[].id'`.
`models MODEL --json` filters the JSON to that exact id; for `models` the
filters are display-only, so `--json` cannot be combined with them. Note
`props --json` includes the full `chat_template`.

`models` prints one quoted id per line by default; `--show-modalities`
and `--show-meta` (with `--meta-fields`) switch it to an aligned table.
`models --reload` refreshes the registry from the server's models dir
without a restart: loaded models whose source was updated or removed are
unloaded, and nothing is loaded.

`load MODEL` and `unload MODEL` are the remaining mutating commands
(router mode only). `load` spawns the model's instance and returns as soon
as it starts (state loading — wait for ready with `slots MODEL
--autoload`); at the router's `--models-max` capacity it evicts the LRU
running model first. `unload` stops the instance and frees its memory,
interrupting any in-flight generation; unless `--force`, it first checks
the model's slots and refuses while one is processing (the check is
best-effort: a request can start between the check and the unload).

`slots` and `props` never load a model by default (they send
`autoload=false`); `--autoload` opts in and holds the request until the
model is loaded (300 s read).

`status` is a watch-friendly board of the models that are actually loaded
(make it a poor man's top with `watch -n 1 llama-server-tool status`); it
opens with the router process itself (the `llama-server` header, port from
the server URL), finds each subprocess's PID/port for the per-model memory
lines, and degrades gracefully when `/proc` or `nvidia-smi` are unavailable.

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
autoload=...)`, `get_metrics(model=...)`, `get_slots(model=...,
autoload=...)`, `load_model(model=..., timeout=...)`,
`unload_model(model=..., force=...)`, plus the models (`Health`,
`ModelList`, `Props`, `MetricsReport`, `SlotsReport`, `LoadReport`,
`UnloadReport`) and `ApiError` / `ServerError`.

Every function also has an async twin for asyncio code — `aget_health()`,
`aget_models()`, `aget_props(...)`, `aget_metrics(...)`, `aget_slots(...)`,
`aload_model(...)`, `aunload_model(...)` — with identical behavior and
return types.

`get_props(model=..., autoload=True)` (and its async twin) holds the request
until the server has loaded the model, so it uses a 5-minute read timeout in
that case (override with `timeout=`).

## Development

```sh
make            # list targets
make test       # static pipeline (ruff, bandit, vulture, refurb, ty, ...) + pytest
```

Tests need no running server (HTTP is mocked). Planning documents for each
phase live in `docs/`.

## License

[0BSD](LICENSE)
