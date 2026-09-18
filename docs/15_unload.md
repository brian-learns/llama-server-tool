# Phase 15: `unload` command (POST `/models/unload`)

## Goal

Replace `kill -9` with a proper unload: `llama-server-tool unload MODEL`
posts `{"model": "<id>"}` to `/models/unload` on the router.

## Endpoint (source-verified, `src/tools/server/`)

- **Router mode only** — registered in the "custom routes for router"
  block (`server.cpp:241`); handler `post_router_models_unload`
  (`server-models.cpp:2087`).
- Request: `POST /models/unload`, JSON body `{"model": "<id>"}`.
- Responses:
  - `200 {"success": true}` — unloaded (or download cancelled: a model in
    `DOWNLOADING` state is unloadable — this endpoint doubles as the
    documented "cancel model downloading" mechanism).
  - `400 {"error": {"code": 400, "message": "model is not found" |
    "model is not running", "type": "invalid_request_error"}}` — the
    standard `res_err` wrapper, i.e. the same shape `ApiError` already
    parses. (Empty/missing `model` field → "model is not found".)
- Unloading is synchronous on the server side (the instance is stopped
  before the response) and interrupts any in-flight generation on that
  model's slots.

This is the second mutating endpoint (after `models --reload`) and the
first POST in the tool.

## Design

### `server.py` — POST support

- New `post_json(base, path, body, timeout=None) -> tuple[int, dict]` and
  async `apost_json(...)` — mirror `fetch_json`/`afetch_json`: same
  `httpx.post(url, json=body, timeout=_request_timeout(timeout))` error
  mapping (`TimeoutException`/`HTTPError` → `ServerError`), same
  `ValueError` → `ServerError("invalid JSON from <path>: ...")`.
- GET helpers untouched.

### `unload.py` (module docstring = the stub's README section)

- `UnloadReport` model: `success: bool = False`,
  `error: ApiError | None = None`, `model: str | None = None`
  (the requested id, set by the API function for the success line),
  `busy_slots: int | None = None` (set when the unload was refused).
  - `render()`: error → `unload: <error.message>`; refused →
    `unload: <model> is busy (<n> slot(s) processing); use --force to
    unload anyway`; success → `unload: <model> unloaded`.
- **Busy pre-check (user decision)**: unless `force`, `unload_model`
  first fetches `get_slots(server, model=..., autoload=False)`; if the
  fetch succeeds and any slot has `is_processing`, it refuses (no POST)
  with the busy report. Idle slots holding a cached context are not
  "busy" (cache loss only). If the slots fetch returns an error body
  (model not running) or nothing is processing, the POST proceeds and
  the server decides. Best-effort: a request can start between check and
  unload.
- **`autoload=false` is mandatory for the check**: router proxy routes
  (`/slots`, `/metrics`, ...) auto-load a non-running model by default
  (`is_autoload` → server default; `server-models.cpp:1868,1951`). A
  plain `get_slots` in the pre-check would *load* the model just to
  unload it. `?autoload=false` makes the check side-effect-free: not
  loaded → 400 "model is not loaded" (no load), loaded → normal slots.
  `get_slots`/`aget_slots` gain `autoload: bool | None = None`
  (`None` = omit the param = server default = current command behavior;
  `True`/`False` = explicit). The `slots` command keeps the default.
- `_unload_from(status, body, model)` — validate the body as
  `UnloadReport` (success and error shapes both validate; anything else →
  `ServerError("invalid response body: ...")`, the usual wrap).
- `unload_model(model: str, server: str | None = None, force: bool =
  False) -> UnloadReport` and `aunload_model(...)` — wrappers over
  `get_slots`/`aget_slots` + `post_json`/`apost_json` sharing
  `_unload_from` (async parity convention).
- No `--json`: the body is `{"success": true}` — nothing to be raw about.
- No confirmation prompt (consistent with `--reload`: an explicit command
  is the opt-in); the busy check is the guard, `--force` the override.

### CLI (`__main__.py`)

```
unload MODEL [--server URL] [--force]
```
- `MODEL` required positional (exact id).
- `--force`: "Unload even if a slot is actively generating (the check is
  best-effort)."
- `ServerError` → stderr + exit 1; `.error` set or refused (busy) →
  render + exit 1; success → render + exit 0. Same shape as the other
  commands.

### Exports

`__init__.py`: `UnloadReport`, `unload_model`, `aunload_model` (+`__all__`).

## Tests

- `helpers.py`: `FakeGet.__call__` gains `json=None` (recorded on the
  fake) — backward compatible.
- model: success body; 400 error body (both messages); unexpected body.
- API (sync): monkeypatched `httpx.post` — URL is `<server>/models/unload`,
  `json == {"model": <id>}`; success → `report.success` and the success
  line; error body → `report.error` set; `httpx.ConnectError` →
  `ServerError`.
- async: `aunload_model` parity (URL + body + both outcomes).
- CLI: success (exit 0, `unload: <id> unloaded`); "model is not running"
  (exit 1, rendered); "model is not found" (exit 1); connection error
  (stderr, exit 1); missing MODEL → typer usage error.
- `test_slots.py`: `autoload` param — `None` omits it (current
  behavior), `False`/`True` send `autoload=false`/`autoload=true`.
- `test_cli.py`: bare invocation list gains `unload`.

## Verification

- `make test`.
- Live (router `:9931`) — test model: **`MiniCPM5-2B`** (small, user
  approved); never touch `Qwen3.8-27B` (serves the active agent session):
  1. error paths first (no state change): `unload MiniCPM5-2B` while not
     loaded → slots check gets 400 "model is not loaded" (no load
     triggered — verify via `models --loaded` that it is *still* not
     loaded), then POST → `unload: model is not running`, exit 1;
     `unload nosuchmodel` → `unload: model is not found`, exit 1.
  2. busy refusal: load `MiniCPM5-2B` (`props MiniCPM5-2B --autoload`),
     start a background generation (curl `/completion`), `unload
     MiniCPM5-2B` → refused with busy count, exit 1, model still loaded;
     `unload MiniCPM5-2B --force` → succeeds.
  3. plain success: once idle, `unload MiniCPM5-2B` →
     `unload: MiniCPM5-2B unloaded`, exit 0; `models --loaded` confirms.

## Docs

README (command table + note), SKILL.md section, AGENTS.md (command list;
convention: first POST + `post_json`; gotchas: mutating, interrupts
in-flight generation, router mode only; **new gotcha**: router proxy
routes auto-load a non-running model by default — `slots MODEL` /
`metrics MODEL` on an unloaded model loads it; `props` already sends
`autoload=false`; `status` is safe because it only slots-fetches models
the registry reports as loaded). Follow-up candidate (out of scope):
`--autoload/--no-autoload` options on the `slots`/`metrics` commands.

## Out of scope

- `--timeout` on unload (default 5 s read applies; the server stops the
  instance before responding — revisit only if a large model ever times
  out).
- Unloading all models / a `load` command (models load via
  `props ?autoload=true` or presets; see Verification: the dev build does
  have a `POST /models/load` handler).
- Non-router (single-model) servers: the endpoint does not exist there
  (501/404 → `ServerError`/error model, degrades fine).

## Verification results (live, router :9931, model `MiniCPM5-2B`)

- Error paths: not loaded → slots check 400 "model is not loaded" (no load
  triggered — `models --loaded` unchanged), POST →
  `unload: model is not running`, exit 1; `unload nosuchmodel` →
  `unload: model is not found`, exit 1. ✓
- Busy refusal: loaded via `props MiniCPM5-2B --autoload`, background
  `curl /completion` (body `"model"` field) →
  `unload: MiniCPM5-2B is busy (1 slot(s) processing); use --force to
  unload anyway`, exit 1, model still loaded. ✓
- `--force`: `unload: MiniCPM5-2B unloaded`, exit 0; the in-flight
  generation was interrupted (non-streaming curl never got a response). ✓
- Plain success (idle): `unload: MiniCPM5-2B unloaded`, exit 0;
  `models --loaded` confirms. ✓ (Note: `models --loaded` can briefly still
  list a just-unloaded model — the registry status lags the unload
  response by a moment.)
- Source finding: `POST /models/load` exists in the dev build
  (`post_router_models_load`, server-models.cpp) — a `load` command would
  pair with `unload` (recorded in AGENTS.md open items).
