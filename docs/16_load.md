# Phase 16: `load` command (POST `/models/load`) + props/slots CLI parity

## Goal

Pair with phase 15: `llama-server-tool load MODEL` posts
`{"model": "<id>"}` to `/models/load` on the router. While at it, make the
`props` and `slots` CLI options parity: both get the explicit
`--autoload/--no-autoload` pair (default `no-autoload`) and `--json`, and
`props` drops its `--timeout` flag (only `load` keeps a timeout option).

The parity change makes the CLI side-effect-free by default: today
`slots MODEL` omits the param and the router **auto-loads** a non-running
model (the phase 15 gotcha); after this change the CLI always sends an
explicit `autoload=false|true`, and loading is opt-in — either via
`--autoload` or the dedicated `load` command.

## Endpoint (source-verified, `src/tools/server/`)

- **Router mode only** — `server.cpp:240`; handler
  `post_router_models_load` (`server-models.cpp:1993`).
- Request: `POST /models/load`, JSON body `{"model": "<id>"}` (aliases
  resolve through the registry).
- Responses:
  - `200 {"success": true}` — **fire-and-launch**: `server_models::load`
    spawns the subprocess, sets the state to `LOADING`, and returns; the
    model is **not ready** when the response arrives. Waiting for ready is
    a separate call that holds: `slots MODEL --autoload` /
    `props MODEL --autoload` (`ensure_model_ready`).
  - `404 {"error": {"code": 404, "message": "model is not found",
    "type": "not_found_error"}}` — note: 404 (unlike `unload`'s 400).
  - `400 {"error": {..., "message": "model is already running", ...}}` —
    `is_running()` covers `LOADED | LOADING | SLEEPING`
    (`server-models.h:94`), so a model mid-load or asleep is refused here
    (a sleeping model wakes on a routed request, not via this endpoint).
  - Exceptions (`ex_wrapper` → the same `{"error": {...}}` shape):
    `"model limit reached, try again later"` (500, `server_error`) when
    `--models-max` capacity cannot be made, `"failed to get a port
    number"`, and a race-condition `"model is not found"`.
- **LRU eviction side effect**: `server_models::load` calls
  `unload_lru()` first — at `--models-max` capacity a *running* model is
  evicted to make room (the dev router runs `--models-max 3`).
- A model in `DOWNLOADING`/`DOWNLOADED` state is "not ready" and the load
  is a **success no-op** (returns `{"success": true}` without loading).

## Design

### `load.py` (user stub exists — keep the docstring, add notes)

- `LoadReport`: `success: bool = False`, `error: ApiError | None = None`,
  `model: str | None = None`; `render()`: error → `load: <error.message>`;
  success → `load: <model> loading` (the state the response leaves the
  model in). No `busy_slots` — loading interrupts nothing.
- `_load_from(status, body, model)` — same shape as `_unload_from`
  (non-200 without an `error` key → `ServerError`; `ValidationError` →
  `ServerError("invalid response body: ...")`).
- `_load_timeout(timeout)` — read timeout = explicit `timeout`, else
  `AUTOLOAD_TIMEOUT` (300 s). The 300 s default is per the phase goal
  (longer default + `--timeout` flag on `load`); in practice the
  fire-and-launch response is quick — the long read covers the cases where
  `load` blocks server-side (`unload_lru()` unloading a running model at
  capacity, waiting out an in-progress reload).
- `load_model(model: str, server: str | None = None, timeout: float |
  None = None) -> LoadReport` and `aload_model(...)` — wrappers over
  `post_json`/`apost_json` sharing `_load_from` (async parity convention).
- No `--json` (body is `{"success": true}`), no busy check.

### CLI (`__main__.py`)

- `load MODEL [--server URL] [--timeout SECONDS]` — inserted before
  `unload`. Help notes: fire-and-launch (wait for ready via
  `slots MODEL --autoload`), LRU eviction at `--models-max`.
  `ServerError` → stderr + exit 1; `.error` → render + exit 1; success →
  render + exit 0 (same shape as `unload`).
- `props`: **drop the `--timeout` option** (the API keeps `timeout=`).
  `--autoload` help gains the hold note: the request waits for the load
  (300 s read timeout by the API default — behavior unchanged, the flag
  was only an override).
- `slots`: **add `autoload: bool = typer.Option(False, ...)`** (typer
  renders the `--no-autoload` pair and `[default: no-autoload]`
  automatically — same as `props` today). The CLI now always passes an
  explicit `False`/`True` to the API.

### `slots.py`

- `_slots_timeout(autoload)` — read timeout = `AUTOLOAD_TIMEOUT` (300 s)
  when `autoload is True`, else the 5 s default (mirrors
  `_props_timeout` without the override param, which the CLI no longer has
  for slots).
- Decision: `slots MODEL --autoload` holds until the load finishes, so it
  needs the long read timeout or real loads would die at 5 s. The API
  keeps `autoload=None` = omit the param = server default (5 s read —
  unchanged for programmatic callers; the CLI no longer produces `None`).
- `props.py` untouched (API surface keeps `autoload` + `timeout`).

### Exports

`__init__.py`: `LoadReport`, `load_model`, `aload_model` (+`__all__`).

## Tests

- `tests/test_load.py` (NEW, mirrors `test_unload.py`; the slots-check
  `env()` is not needed — `load` makes a single POST):
  - success: POST URL `<server>/models/load`,
    `json_body == {"model": "m"}`; default read timeout 300
    (`FakeGet.timeout.read == 300.0`), `timeout=60` → 60.
  - 404 not found (code 404, `not_found_error`) → `.error` set,
    render `load: model is not found`.
  - 400 "model is already running" → `.error` set.
  - 500 "model limit reached, try again later" (`server_error`) →
    `.error` set (the LRU-eviction case).
  - unexpected body → `ServerError("invalid response body")`; transport →
    `ServerError`.
  - CLI: success (exit 0, `load: m loading`); not found / already running
    (exit 1, rendered); `--timeout 60` reaches the POST; missing MODEL →
    exit 2.
- `tests/test_async_api.py`: `aload_model` success (FakeAsyncClient.post
  records `(url, json)`); parity pair on the 404 body.
- `tests/test_slots.py`:
  - `test_slots_model_param` updated: CLI `slots foo` →
    `{"model": "foo", "autoload": "false"}`; bare `slots` →
    `{"autoload": "false"}`.
  - new: CLI `--autoload` → `autoload: "true"` + `timeout.read == 300.0`;
    default → `timeout.read == 5.0`.
  - API `autoload` param test unchanged (`None` still omits).
- `tests/test_props.py`: `--timeout` CLI flag tests removed/updated (API
  `timeout=` tests stay); `props MODEL --autoload` → 300 s read.
- `tests/test_cli.py`: bare-invocation list gains `load`.

## Verification (live, router `:9931`, model `MiniCPM5-2B`)

Safety: the dev router runs `--models-max 3`; with only `Qwen3.8-27B`
loaded (1/3), loading `MiniCPM5-2B` reaches 2/3 — **no LRU eviction**.
Never run a test that would load a 4th model (eviction could take the
session model).

1. `load nosuchmodel` → `load: model is not found` (404), exit 1.
2. `load MiniCPM5-2B` → `load: MiniCPM5-2B loading`, exit 0; then
   `slots MiniCPM5-2B --autoload` (holds until ready) prints slots and
   `models --loaded` lists it.
3. `load MiniCPM5-2B` again → `load: model is already running`, exit 1.
4. `unload MiniCPM5-2B` → back to the starting state.
5. Parity CLI: while not loaded, `slots MiniCPM5-2B` →
   `slots: model is not loaded`, exit 1, and it is **still not loaded**
   (the CLI no longer auto-loads — the gotcha is fixed);
   `props MiniCPM5-2B` stays read-only; `props MiniCPM5-2B --autoload`
   loads (300 s hold); `unload MiniCPM5-2B` to clean up.

## Docs

- README: command table row for `load`; the mutating-commands paragraph
  gains `load` (spawns a model; LRU eviction at capacity); API lists gain
  `load_model`/`aload_model`/`LoadReport` and the `slots` `autoload` note;
  note that the `slots`/`props` CLI no longer auto-loads by default.
- SKILL.md: `load` section (fire-and-launch, wait-for-ready workflow,
  LRU-eviction warning); `slots` section gains `--autoload` + the
  side-effect-free default; `props` section drops `--timeout`.
- AGENTS.md: command list; conventions (slots CLI always sends an
  explicit autoload; the `--autoload/--no-autoload` follow-up is done for
  `slots`); gotchas (load is fire-and-launch; `is_running` includes
  LOADING/SLEEPING; 404 vs unload's 400; LRU eviction at `--models-max`;
  the proxy-route auto-load gotcha now says the CLI is safe by default,
  only API callers who omit `autoload` still trigger it); open items lose
  the `POST /models/load` entry (implemented).

## Out of scope

- Waiting-for-ready inside `load` (no polling loop) — the documented
  workflow is `load MODEL` then `slots MODEL --autoload`.
- `--autoload` on the `metrics` command (the `slots` half of the phase 15
  follow-up is done; `metrics` can follow the same pattern later).
- Loading via `--models-max`-aware eviction policy (the server's LRU is
  the policy; the tool just documents it).

## Verification results (live, router :9931, model `MiniCPM5-2B`)

- `load nosuchmodel` → `load: File Not Found`, exit 1 (404
  `not_found_error`). Note: the *deployed* dev binary phrases the
  not-found message "File Not Found"; the source read for this plan says
  "model is not found" — same shape, handled identically.
- `load MiniCPM5-2B` → `load: MiniCPM5-2B loading`, exit 0;
  `slots MiniCPM5-2B --autoload` held until ready and printed the slots;
  `models --loaded` listed it. ✓ (One probe curl hit the endpoint directly
  and did the first load — the tool's own success line was then verified
  on a second load cycle.)
- `load MiniCPM5-2B` while running → `load: model is already running`,
  exit 1. ✓
- `unload MiniCPM5-2B` → back to the starting state (1/3 capacity). ✓
- Parity CLI: while not loaded, `slots MiniCPM5-2B` →
  `slots: model is not loaded`, exit 1, **still not loaded** (the CLI
  no longer auto-loads); `props MiniCPM5-2B` →
  `props: model is not loaded`, exit 1, still not loaded;
  `props MiniCPM5-2B --autoload` loaded (holding request) and printed the
  report; `unload` cleaned up. ✓
