# Phase 1: `health`

Plan for the first real command: `llama-server-tool health`.

## CLI

```
llama-server-tool health [--server URL]
```

- `--server` — full base URL of the llama-server, e.g. `http://127.0.0.0:8080`
- `LLAMA_SERVER_URL` env var — same value, lower priority than `--server`
- Default: `http://127.0.0.0:8080` (per `docs/01_initial_plan.md`)

The URL is used as-is; a trailing `/` is stripped before appending the endpoint path.
This resolution logic will be reused by `models`, `props`, and `metrics`, so it lives in
`__main__.py` as a small helper for now and gets extracted to a shared module when the
second command lands.

## Dependency

Add `httpx` to `dependencies` in `pyproject.toml` (`uv add httpx --exclude-newer "7 days"`),
then re-lock.

## Behavior

`GET {server}/health` (the endpoint is public, no API key needed).

| Case | Output (stdout unless noted) | Exit code |
|------|------------------------------|-----------|
| `200 {"status": "ok"}` | `health: ok` | 0 |
| `503 {"error": {...}}` | `health: <message>` (e.g. `health: Loading model`) | 1 |
| Connection error / timeout (5 s) | `health: <error detail>` to stderr | 1 |
| Unexpected body / status | raw detail to stderr | 1 |

## Code shape (per AGENTS.md conventions)

- `health.py` — pydantic model(s) own parsing + rendering:
  - a body model with `status: str | None` and `error: HealthError | None`, where
    `HealthError` is `{code: int, message: str, type: str}`
  - `render() -> str` produces the `health: ...` line
- `__main__.py` — thin `health` command:
  - resolve server URL (`--server` → `LLAMA_SERVER_URL` → default)
  - `httpx.get(f"{base}/health", timeout=5.0)`
  - parse JSON into the model; `ValidationError` → message to stderr + `typer.Exit(code=1)`
  - `httpx.HTTPError` (connection refused, timeout, ...) → stderr + exit 1
  - non-200 without a parseable error body → stderr + exit 1
  - on success: `typer.echo(model.render())`; exit 1 for the 503 case
- The template `greet` command and `tests/test_greet.py` are removed; `health` replaces
  them as the first real command.

## Tests (`tests/test_health.py`)

CLI behavior via `typer.testing.CliRunner`, with `httpx` mocked (monkeypatch the client
call in `__main__`):

1. `200 ok` → exit 0, `health: ok` on stdout
2. `503` with `{"error": {"message": "Loading model", ...}}` → exit 1, message shown
3. `httpx.ConnectError` → exit 1, message on stderr
4. `--server` overrides default URL (assert the mocked URL used)
5. `LLAMA_SERVER_URL` used when `--server` absent; `--server` wins when both set
6. trailing `/` on `--server` does not produce `//health`
7. malformed JSON body → exit 1, error on stderr

Model tests (direct): rendering of ok and error bodies.

## Verification

`make test` (ruff, bandit, vulture, refurb, ty, interrogate, uv audit, pytest).

## Out of scope for this phase

- `models`, `props`, `metrics` commands
- API key support, streaming, retries
