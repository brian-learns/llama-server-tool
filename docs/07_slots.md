# Phase 6: `slots`

Plan for the fifth command: `llama-server-tool slots` — the "what's actually
busy right now" view for router-mode setups.

## CLI

```
llama-server-tool slots [--model ID]
```

- `--model` — passed as `?model=<id>`. Optional (a plain single-model server
  answers `/slots` without it), but in router mode the server answers 400
  without it — same behavior as `metrics`.
- `--server` / `LLAMA_SERVER_URL` / default as with the other commands.
- Command help line (list + `--help` first line):
  `Show slot state via GET /slots?model=<id> [--model ID].`

## Endpoint

`GET {server}/slots` — returns a **JSON array** of slot objects (not a wrapped
object). Per the docstring in `slots.py`: `id`, `id_task`, `n_ctx`,
`speculative`, `is_processing`, `params` (same shape as the props
generation-params object), `next_token`
(`has_next_token`, `has_new_line`, `n_remain`, `n_decoded`).

## Code shape

- `slots.py` — pydantic models + `get_slots()`, per the established pattern:
  - `Slot`: all fields optional (lenient, as with `Props`):
    `id, id_task, n_ctx, speculative, is_processing, params, next_token`
  - `SlotNextToken`: `has_next_token, has_new_line, n_remain, n_decoded`
    (all optional)
  - `SlotsReport`: `slots: list[Slot] = []`, `error: ApiError | None`
  - `get_slots(server=None, model=None) -> SlotsReport`:
    - `params = {"model": model} if model is not None else None`
    - uses `fetch()` + `json.loads` directly (the body is a list, not a dict,
      so `fetch_json` doesn't fit); non-list body → `ServerError`
    - non-200: JSON error body → `SlotsReport` with `.error` set (400
      missing-model, 503 `fail_on_no_slot`, ...); non-JSON →
      `ServerError("HTTP <status>: <body>")` — same split as `get_metrics`
  - `render()` — compact, one block per slot, only present fields:

    ```
    slots (Ornith-1.0-9B):
      slot 0:
        is_processing: true
        n_ctx:         65536
        speculative:   false
        id_task:       135
        n_decoded:     136
    ```

  - header is `slots:` without `--model`; `n_decoded`/`n_remain` are flattened
    from `next_token`; error bodies render `slots: <message>`
  - **`params` is not rendered in v1** (see out of scope) — `Slot.params` is
    parsed into the existing `GenerationParams` (imported from `props.py`) so
    the data is available to automation and a later `--params` flag has
    nothing new to build
- `__main__.py` — thin `slots` command (catch `ServerError` → stderr + exit 1;
  render; exit 1 when `.error` set)
- `__init__.py` — export `get_slots` and `SlotsReport` (+ `Slot`), update
  `__all__`

## Tests (`tests/test_slots.py`)

CLI (via `CliRunner` + `FakeGet`):

1. `200` two-slot array (one busy, one idle) → exit 0, both blocks rendered,
   busy slot shows `is_processing: true` + `n_decoded`
2. `--model foo` → URL `/slots` with `model=foo`; no `--model` → no params
3. `400` JSON error (router mode, missing model) → exit 1, `slots: <message>`
4. connection error → exit 1, stderr
5. `200 []` (empty list) → exit 0, output is just `slots:` (or `slots (x):`)
6. `200` non-list JSON (e.g. an object) → exit 1, stderr

Model/API tests (direct):

7. full two-slot fixture renders the expected report exactly
8. slot with all-optional fields absent renders without crashing
9. `params` parses into `GenerationParams` (field access works) but never
   appears in `render()` output
10. `get_slots` 503 JSON error → `.error` set, no raise
11. `from llama_server_tool import get_slots, SlotsReport, Slot` works

## Doc sync

- `README.md` — add `slots` row to the command table
- `SKILL.md` — add a `slots` section (short, like the others)
- `AGENTS.md` — add `slots` to the command list in "What this is"

## Live finding (implemented)

On the dev server, `next_token` is a **list** (one entry per in-flight
sequence) on some models and a plain object on others. `Slot.next_token`
accepts `SlotNextToken | list[SlotNextToken] | None` and renders the first
entry.

## Verification

- `make test`
- live: `uv run llama-server-tool slots --model Ornith-1.0-9B` and the 400
  path without `--model` (numbers/booleans only — session-safe)

## Out of scope for this phase

- rendering per-slot `params` / filter options (waiting on your feedback for
  `models`; likely the same treatment for `slots`)
- `?fail_on_no_slot=1` support
- POST `/slots/{id}` (slot configuration)
