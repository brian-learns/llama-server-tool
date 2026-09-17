# Phase 8: async API

Add async twins for the five API functions so the tool can be driven from an
asyncio framework without blocking the event loop.

## Motivation

The consuming orchestrator is mostly async. It pulls data about the models and
injects it into `TRACE_EXPERIMENT` / logged data. Today the only entry points
are sync (`get_props`, ...), which do a blocking `httpx.get`. That is
especially costly for `get_props(model=..., autoload=True)`, which blocks until
the server has loaded the model into memory. Real async transport (an
`httpx.AsyncClient`) keeps the loop free and allows concurrent requests
(parallel warm-up, fanning out over several servers).

## Public API

New async functions, one per operation, same signatures and return types as
the sync ones:

```python
from llama_server_tool import (
    aget_health,   # (server=None) -> Health
    aget_models,   # (server=None) -> ModelList
    aget_props,    # (server=None, model=None, autoload=False) -> Props
    aget_metrics,  # (server=None, model=None) -> MetricsReport
    aget_slots,    # (server=None, model=None) -> SlotsReport
)
```

```python
import asyncio
from llama_server_tool import aget_models, aget_props

async def main() -> None:
    models = await aget_models()
    props = await aget_props(model="Qwen3.8-27B")   # autoload defaults to False
    payload = props.model_dump(mode="json")         # serializable for tracing
    # ... inject payload into TRACE_EXPERIMENT / logged data ...

asyncio.run(main())
```

- Return types are the **same pydantic models** as the sync API — no new model
  classes — so any code that handles a sync result handles an async result
  unchanged.
- For logging/tracing, models serialize directly: `.model_dump(mode="json")`
  (or `.model_dump_json()`). This is the intended injection path.
- Error semantics are identical to the sync API: a well-formed API error body
  comes back as a model with `.error` set (no raise); transport/parse failures
  raise `ServerError`.

## Design (no logic duplication)

The sync and async paths must behave identically, so the "status/body → model"
branching is extracted once and shared; only the transport line differs.

### `server.py` — async transport

```python
async def afetch(base, path, params=None) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(f"{base}{path}", params=params)
        except httpx.HTTPError as err:
            raise ServerError(str(err)) from err
    return response.status_code, response.text

async def afetch_json(base, path, params=None) -> tuple[int, dict]:
    status, text = await afetch(base, path, params=params)
    try:
        return status, json.loads(text)
    except ValueError as err:
        raise ServerError(f"invalid JSON from {path}: {err}") from err
```

A fresh `AsyncClient` is created per call (matches the per-call nature of the
sync `httpx.get`); connection pooling / a persistent client is out of scope.

### Per-endpoint modules — extract a private parse helper

Each module gets a private `_x_from(...)` that owns the current
validate/branch logic, and the sync + async public functions become thin:

```python
# props.py (representative)
def _props_from(body) -> Props:
    try:
        return Props.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err

def get_props(server=None, model=None, autoload=False) -> Props:
    params = None if model is None else {"model": model, "autoload": "true" if autoload else "false"}
    _, body = fetch_json(resolve_server_url(server), "/props", params=params)
    return _props_from(body)

async def aget_props(server=None, model=None, autoload=False) -> Props:
    params = None if model is None else {"model": model, "autoload": "true" if autoload else "false"}
    _, body = await afetch_json(resolve_server_url(server), "/props", params=params)
    return _props_from(body)
```

Same shape for the other four:

- `health.py` — `_health_from(body) -> Health`
- `models.py` — `_models_from(body) -> ModelList`
- `metrics.py` — `_metrics_from(status, text) -> MetricsReport` (keeps the
  non-200 JSON-vs-text branch)
- `slots.py` — `_slots_from(status, text, model) -> SlotsReport` (keeps the
  list check + `model_name`)

The one-line `params = ...` is kept inline in each public function (trivial;
keeps each function self-contained).

### `__init__.py`

Re-export the five `aget_*` functions and add them to `__all__`. No new model
exports.

## Static-check risk (vulture)

The CLI (`__main__.py`) only calls the sync functions, so the `aget_*`
functions are referenced only from `__all__` and from tests (which vulture does
not scan). vulture will likely flag them as unused. Mitigation: confirm with
`make check`; if flagged, add the `aget_*` names to the vulture whitelist in
`pyproject.toml`. Do **not** add a throwaway CLI call just to silence it.

## Tests

`tests/helpers.py` — add an async stand-in (reuses the existing
`json_response` / `text_response` builders, which produce plain `httpx.Response`
objects valid for both transports):

```python
class FakeAsyncClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    async def get(self, url, timeout=None, params=None):
        self.calls.append((url, params))
        if self.error is not None:
            raise self.error
        return self.response
```

Tests monkeypatch `llama_server_tool.server.httpx.AsyncClient` with
`FakeAsyncClient` (and keep the sync `httpx.get` fakes for the sync tests).

`tests/test_async_api.py`:

1. `await aget_health()` ok → `Health`, `status == "ok"`; correct URL hit
2. `await aget_health()` 503 → `.error` set (no raise)
3. `await aget_health()` connect error → raises `ServerError`
4. `await aget_models()` → `ModelList` with data
5. `await aget_props(model="x")` → request params `model=x&autoload=false`;
   `autoload=True` → `autoload=true`; no model → no params
6. `await aget_metrics()` ok → `MetricsReport` with families
7. `await aget_metrics()` 501 JSON → `.error` set
8. `await aget_metrics()` non-200 non-JSON → raises `ServerError`
9. `await aget_slots()` ok → `SlotsReport`; `--model`-less → no params
10. `await aget_slots()` non-list body → raises `ServerError`
11. **parity**: for each operation, the async result equals the sync result
    given the same canned body (guards against drift between the two paths)
12. `await aget_props(...).model_dump(mode="json")` round-trips to a JSON
    string (the tracing injection path)

Existing sync tests stay green and unchanged (the refactor must not alter sync
behavior).

## Doc sync

- `README.md` — note the async entry points in the Python API section
- `SKILL.md` — add the `aget_*` functions to the Python API section
- `AGENTS.md` — add the async functions to the "What this is" command→function
  list and a line in Conventions about the shared `_x_from` + sync/async parity

## Verification

- `make test` (full static pipeline + pytest)
- live async smoke (read-only, **no** `autoload=True` — that would pre-warm a
  model): `uv run python -c 'import asyncio; from llama_server_tool import
  aget_models, aget_props; print(asyncio.run((lambda: aget_models())()))'`
  or a small `asyncio.run(main())` snippet; confirm a model's
  `.model_dump(mode="json")` serializes cleanly.

## Out of scope for this phase

- async CLI commands (the CLI stays sync; only the library API gains async)
- persistent/pooled `AsyncClient`, client injection, retries, timeouts beyond
  the existing `REQUEST_TIMEOUT`
- new model classes or changed rendering
