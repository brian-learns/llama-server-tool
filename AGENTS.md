<!--
SPDX-License-Identifier: 0BSD
Copyright (c) 2026 llama_server_tool creators and contributors
-->

# AGENTS.md

Non-obvious details and guidance for AI coding agents working in this repository.

## What this is

A CLI (typer) plus Python API (pydantic models) to administer a local
llama-server. One command per endpoint, same logic importable from the package
root:

- `health` — `GET /health` → `check_health()`
- `models` — `GET /v1/models` → `get_models()`
- `props` — `GET /props` → `get_props(model=..., autoload=...)`
- `metrics` — `GET /metrics` (Prometheus exposition text, parsed via
  `prometheus_client`) → `get_metrics()`

## Development commands

Makefile is (ab)used to run developer commands — `make` to see all targets.

- `make test` — static pipeline (ruff, bandit, vulture, refurb, ty, interrogate,
  audit) then pytest
- `uv run llama-server-tool` — run the CLI (bare invocation lists the commands)
- `uv add <library>` — add a dependency

## Key files

```
scripts/test-all-versions.sh     test on all supported python versions
.github/workflows/ci.yml         CI matrix, mirrors the local version list
docs/NN_*.md                     per-phase planning docs (plan first, code after approval)
src/llama_server_tool/server.py  shared: URL resolution, fetch/fetch_json,
                                 ApiError, ServerError, format_value
src/llama_server_tool/<cmd>.py   one file per endpoint: pydantic models + API
                                 function; the module docstring is the endpoint
                                 documentation (from the llama.cpp server README)
tests/helpers.py                 FakeGet (httpx.get stand-in) + response builders
```

Skills under `src/**/.agents/skills/` document how to *use* the tool (they ship
in the wheel); this file covers *developing* it.

## Conventions

- **Layering**: `server.py` (HTTP + shared models) → per-endpoint module
  (pydantic models with `render()` + a `get_*`/`check_*` API function) →
  `__main__.py` (thin typer glue) → `__init__.py` (public API re-exports +
  `__all__`). typer owns the interface (options, help, exit codes); pydantic
  owns the domain (validation, rendering).
- **Error semantics**: well-formed API error bodies (503, 501, 400-JSON, ...)
  come back as models with `.error` set (shared `ApiError`) — no exception for
  those. Everything else (connection, timeout, invalid JSON, unexpected body,
  non-JSON error responses) raises `ServerError`; API functions wrap pydantic
  `ValidationError` as `ServerError("invalid response body: ...")`. Commands
  catch `ServerError` → stderr + `typer.Exit(1)`, render the model, and exit 1
  when `.error` is set (or `status != "ok"` for health).
- **typer**: keep the explicit root `@app.callback(invoke_without_command=True)`
  — it prints the command list on bare invocation and prevents typer from
  collapsing a single command into the root.
- **pydantic**: use `mode="before"` validators when normalization must happen
  *before* field constraints. Plain functions work as validators (pydantic v2);
  they avoid vulture flagging an unused `cls` — but ruff N805 misfires on them
  in class scope, so keep the `# noqa: N805` with a short reason.
- **Tests**: no live server is ever required — monkeypatch `httpx.get` with
  `FakeGet` from `tests/helpers.py` (records URLs and query params). CLI via
  `typer.testing.CliRunner` (assert `exit_code` and `output`/`stderr`); models
  and API functions directly; `pytest.raises` for expected `ServerError`s.

## Safety

- **Never print or paste a raw `/props` response.** `chat_template` is a raw
  Jinja2 system-prompt template and dumping it has crashed agent sessions.
  `Props.render()` deliberately shows only `<hidden: N chars>`; keep it that
  way, and don't curl `/props` during development — use synthetic fixtures.
- `props` must default to `autoload=false` when a model is given:
  `?model=<id>` without it makes the server load the model into memory and
  pre-warm it.
- `/metrics` output is numbers only — safe to inspect live.

## Workflow

*Plan* (write `docs/NN_topic.md`), *Do* (code after user approves the plan),
*Check* (user checks before git commit), *Act* (commit after approval).

## Gotchas

- `uv` >= 0.12 is required (checked by `make checkdeps`); the audit and
  malware-check flags are preview features.
- Venvs (`.venv`, `.venv-*`) and tool caches are gitignored — never commit
  them; `make clean` removes the caches.
- The last version in the script runs in the dev `.venv` and must match
  `.python-version`; the others get `UV_PROJECT_ENVIRONMENT=".venv-<ver>"`
  envs. Never run a bare `uv run --python <older>` — it would recreate the
  dev `.venv` with that interpreter.
- Dependency resolution uses `exclude-newer = "7 days"` (see `[tool.uv]`);
  `uv lock --check` in `make check` enforces it. CI installs with
  `uv sync --frozen` against the committed lockfile.
- `prometheus_client`'s parser quirk: it strips the counter `_total` suffix
  from family names (sample names keep it — `parse_exposition` prefers those)
  and the help text lives in `Metric.documentation`, not `.help`.
- The dev server runs in router mode with many registered models: `/v1/models`
  returns a long list (not the single element the llama.cpp README describes),
  and `/metrics` requires `?model=<id>`. `/metrics` only exists if the server
  was started with `--metrics` (otherwise 501 JSON error body).
