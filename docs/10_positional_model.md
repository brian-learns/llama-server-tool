# Phase 10: positional model argument

Change the CLI so the model is a positional argument instead of a `--model`
option.

## Current → desired

| command | now | after |
| ------- | --- | ----- |
| `health` | — | unchanged |
| `models` | `models` (full list) | `models [MODEL]` — **client-side filter** (the endpoint returns the whole registry) |
| `props` | `props --model <id>` | `props [MODEL]` (server-side `?model=<id>`) |
| `metrics` | `metrics --model <id>` | `metrics [MODEL]` (server-side `?model=<id>`) |
| `slots` | `slots --model <id>` | `slots [MODEL]` (server-side `?model=<id>`) |

```
llama-server-tool models                          # same as today
llama-server-tool models SomeModel                # new: filter to matching model(s)
llama-server-tool props unsloth/gemma-...-GGUF:MXFP4_MOE     # was: --model ...
llama-server-tool props SomeModel --autoload --timeout 60    # options still work
llama-server-tool health                          # unchanged
```

Decisions (confirmed with the user):

1. `models [MODEL]` is a **client-side filter**: exact id match only
   (case-sensitive); no match → `models: no model with id '<query>'` on
   stderr, exit 1. (Original proposal was exact-then-substring; the user
   approved exact match only — broader filters are a later phase.)
2. `--model` is **removed from the CLI** (no alias) — pre-1.0 clean break.
   The **Python API keeps the `model=` keyword** on `get_props` /
   `get_metrics` / `get_slots` (and their async twins); `get_models` gains no
   parameter — filtering stays CLI-side.
3. The argument stays **optional** for `metrics`/`slots` at the CLI level: the
   *server* requires it in router mode (400 without it); the tool must still
   work against a plain single-model server.

## Code shape

- `models.py` — `ModelList` gains:

  ```python
  def match(self, query: str) -> "ModelList":
      """Return only the entries whose id equals the query (exact match)."""
  ```

  returns a new `ModelList` (same `error` passthrough not needed — the CLI
  only filters after a successful fetch).
- `__main__.py` — per command:

  ```python
  @app.command()
  def props(
      model: str | None = typer.Argument(None, help="Model id to query (required in router mode)."),
      server: str | None = typer.Option(None, help="Base URL of the llama-server."),
      autoload: bool = typer.Option(False, help="..."),
      timeout: float | None = typer.Option(None, help="..."),
  ) -> None:
  ```

  - `models`: `result = get_models(server)`; when `model` given,
    `result = result.match(model)`; empty result → stderr + `typer.Exit(1)`;
    then render/exit as today
  - `props`/`metrics`/`slots`: pass the positional through to the existing API
    call (`get_props(server, model=model, ...)` — no API change)
  - short help lines: `[--model ID]` → `[MODEL]`, keep the `?model=<id>`
    annotation, e.g.
    `Show server properties via GET /props?model=<id> [MODEL].`
    and `models`: `Show the loaded model via GET /v1/models [MODEL].`

## Tests

- `tests/test_models.py` — CLI: `models` with positional filters to the
  matching entry (other entries absent); `--server` still works as an option
  with a positional present; no-arg behavior unchanged. New model tests for
  `ModelList.match`: exact match, no match → empty list, case-sensitivity.
- `tests/test_props.py` / `test_metrics.py` / `test_slots.py` — existing
  `--model foo` invocations become positional `foo`; assertions on URL/params
  unchanged (the server-side behavior is identical). Add one test each that
  options still parse with a positional present (`props x --autoload`).
- `tests/test_api.py` / `test_async_api.py` — unchanged (API keeps `model=`).
- `tests/test_cli.py` — command list unchanged.

## Doc sync

- `README.md` — command table + Python API note: CLI takes the model as a
  positional; `models [MODEL]` filters client-side
- `SKILL.md` — all example commands updated to the positional form
- `AGENTS.md` — CLI examples/conventions mention the positional argument

## Verification

- `make test`
- live: `uv run llama-server-tool models Qwen3.8-27B` (exact),
  `models nosuchmodel` (exit 1), `props Qwen3.8-27B`, `slots Qwen3.8-27B`,
  `metrics Qwen3.8-27B`

## Out of scope

- the broader `models` output filters the user has in mind (this lands the
  one positional filter; more filters can build on `ModelList.match`)
- substring/fuzzy/prefix matching for `models [MODEL]`
- `--model` CLI alias
