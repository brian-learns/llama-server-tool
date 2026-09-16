# Phase 5: Python API

Expose the four operations as importable functions for automation, and make the
bare `llama-server-tool` invocation show the command list.

## API surface

`__init__.py` re-exports the public API (py.typed already ships, so it's typed):

```python
from llama_server_tool import (
    check_health,   # (server=None) -> Health
    get_models,     # (server=None) -> ModelList
    get_props,      # (server=None, model=None, autoload=False) -> Props
    get_metrics,    # (server=None, model=None) -> MetricsReport
    Health, ModelList, Props, MetricsReport,
    ApiError, ServerError,
)
```

Usage:

```python
from llama_server_tool import check_health, get_props, ServerError

try:
    result = check_health()                # -> Health
except ServerError as err:                 # transport/parse failure
    raise SystemExit(err)

if result.error is not None:               # well-formed API error, e.g. 503 loading
    raise SystemExit(result.error.message)

props = get_props(model="Qwen3.8-27B")     # autoload defaults to False
print(props.model_path)                    # or props.render() for the CLI report
```

Semantics:

- `server` argument resolves exactly like the CLI option (arg → `LLAMA_SERVER_URL`
  → default)
- functions **return** the validated model; a well-formed API error body (503, 501,
  400-JSON) comes back as a model with `.error` set — no exception for those
- `ServerError` is raised for everything else: connection/timeout, invalid JSON,
  unexpected body shape (wraps the pydantic `ValidationError` message), and
  non-200 responses with non-JSON bodies
- `render()` stays available on the models for a human-readable string

## Refactor

- `health.py` — `check_health(server=None) -> Health`
- `models.py` — `get_models(server=None) -> ModelList`
- `props.py` — `get_props(server=None, model=None, autoload=False) -> Props`
- `metrics.py` — `get_metrics(server=None, model=None) -> MetricsReport`
  - each moves the fetch + validate logic out of `__main__.py`, wraps
    `ValidationError` in `ServerError(f"invalid response body: {err}")`
- `__main__.py` — commands become glue: call the function, catch `ServerError`
  → stderr + `typer.Exit(1)`, `echo(result.render())`, exit 1 when the model
  signals failure (`result.error`, `status != "ok"` / `status != 200`). CLI
  behavior and messages stay identical to phase 1–4 (existing tests must pass
  unchanged)
- `__init__.py` — re-exports + `__all__`

## CLI tweak: bare invocation lists commands

Currently `llama-server-tool` with no command errors: `Missing command.` (exit 2).
Change the existing root callback:

```python
@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Administer a local llama-server."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()
```

Bare invocation now prints the full help (command list) and exits 0. The explicit
callback keeps the subcommand structure (see the comment at the definition).

## Tests

`tests/test_api.py` (direct function calls, `FakeGet` via monkeypatch):

1. `check_health()` ok → `Health` with `status == "ok"`
2. `check_health()` 503 → `Health` with `.error` set (no raise)
3. `check_health()` connect error → raises `ServerError`
4. `get_models()` → `ModelList` with data
5. `get_props(model="x")` → request params `model=x&autoload=false`;
   `autoload=True` → `autoload=true`; no model → no params
6. `get_metrics()` ok → `MetricsReport` with families
7. `get_metrics()` 501 JSON → `MetricsReport` with `.error` set (no raise)
8. `get_metrics()` non-200 non-JSON body → raises `ServerError`
9. re-exports: `from llama_server_tool import check_health, get_models, get_props,
   get_metrics, Health, ModelList, Props, MetricsReport, ApiError, ServerError`
   all importable

`tests/test_health.py` (or a small shared CLI test) — new case:

10. `runner.invoke(app, [])` → exit 0, output contains `Commands` and all four
    command names

Existing CLI tests stay as the behavior-preservation net.

## Verification

- `make test`
- live smoke: `uv run python -c "from llama_server_tool import check_health; print(check_health().render())"`
- bare `uv run llama-server-tool` → command list, exit 0

## Out of scope for this phase

- async API, client/context-manager classes
- PromQL querying of a Prometheus server
- config files / environment beyond `LLAMA_SERVER_URL`
