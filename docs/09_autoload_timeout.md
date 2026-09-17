# Phase 9: autoload timeout

Fix `props --model <id> --autoload` failing with `props: timed out`.

## Problem

With `autoload=true` the server holds the `/props` response until the model is
fully loaded into memory, which takes longer than the flat 5 s timeout.
`httpx.ReadTimeout` (whose `str()` is literally `timed out`) is wrapped as
`ServerError("timed out")` by `server.fetch`. No other endpoint blocks on a
load: `/health` reports loading immediately (503); `/v1/models`, `/metrics`,
and `/slots` answer without waiting.

## Design

### `server.py`

- `CONNECT_TIMEOUT = 5.0`, `AUTOLOAD_TIMEOUT = 300.0` (new constants;
  `REQUEST_TIMEOUT = 5.0` stays the default read timeout)
- `fetch()` / `afetch()` gain `timeout: float | None = None` (read timeout in
  seconds). The request uses `httpx.Timeout(timeout if timeout is not None
  else REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)` so the connect timeout stays
  5 s (fast failure when the server is down) while only the read budget grows
- `fetch_json()` / `afetch_json()` pass `timeout` through
- timeout errors get a useful message: on `httpx.TimeoutException`, raise
  `ServerError(f"timed out after {read}s")` instead of the bare `timed out`

### `props.py`

- `get_props(server=None, model=None, autoload=False, timeout=None)` and
  `aget_props(...)` gain the `timeout` kwarg
- **automatic rule** (applies to both sync and async, so the orchestration's
  `await aget_props(model=..., autoload=True)` benefits with no new argument):
  `autoload=True` and no explicit `timeout` → read timeout
  `AUTOLOAD_TIMEOUT` (300 s); otherwise the default 5 s
- the other four endpoint functions are unchanged (nothing else blocks on a
  load); if one ever needs it, the same one-line pattern applies

### `__main__.py`

- `props` command gains `--timeout` (float, seconds, optional) and passes it
  to `get_props`; `--timeout` always wins over the autoload default

## Behavior

| Call | Read timeout |
| ---- | ------------ |
| `props` / `props --model x` (autoload off) | 5 s |
| `props --model x --autoload` | 300 s |
| `props --model x --autoload --timeout 60` | 60 s |
| `get_props(..., autoload=True)` / `aget_props(..., autoload=True)` | 300 s |
| `get_props(..., autoload=True, timeout=60)` | 60 s |
| any other command | 5 s (unchanged) |

Connect timeout is 5 s in all cases.

## Tests

- extend `FakeGet` / `FakeAsyncClient` in `tests/helpers.py` to record the
  `timeout` passed to httpx (it is passed as an `httpx.Timeout` object; assert
  on `.read`/`.connect`)
- `tests/test_props.py`:
  1. `get_props(model="x")` → recorded read 5.0, connect 5.0
  2. `get_props(model="x", autoload=True)` → read 300.0
  3. `get_props(model="x", autoload=True, timeout=60)` → read 60.0
  4. `aget_props` variants (async fake) → same three cases
  5. CLI: `--autoload` → 300.0; `--autoload --timeout 60` → 60.0;
     `--timeout 60` without `--autoload` → 60.0
  6. `server.fetch` raises `ServerError("timed out after 300.0s")` when the
     fake raises `httpx.ReadTimeout` (and `5.0s` by default)
- existing tests stay green (default behavior unchanged)

## Doc sync

- `README.md` — props section: note `--autoload` waits for the load (default
  5 min read timeout) and `--timeout` overrides
- `SKILL.md` — same note in the props section
- `AGENTS.md` — one line in Conventions or Gotchas: `/props?autoload=true`
  blocks until the model is loaded; the tool uses `AUTOLOAD_TIMEOUT` (300 s)
  for it

## Verification

- `make test`
- live: `uv run llama-server-tool props --model Qwen3.8-27B --autoload`
  (deliberately loads the model — the whole point; expect a longer wait), and
  a bare `props` still fails fast (5 s) against an unreachable server

## Out of scope

- per-endpoint timeouts for the other commands
- progress reporting / polling during a long load
- making `AUTOLOAD_TIMEOUT` configurable via env var
