# Phase 11: raw JSON output (`--json`)

Add a `--json` option to `health`, `models`, `props`, and `slots` that
prints the server's response body exactly as received, instead of the
formatted report. Motivation: the user is porting shell scripts that do
`curl ... | jq ...`; `--json` is the drop-in replacement
(`llama-server-tool models --json | jq ...`), and a full unfiltered dump is
handy when debugging.

## Decisions (confirmed with the user)

1. **Flag name: `--json`**, applied to `health`/`models`/`props`/`slots`.
   The body is printed verbatim — the server's own JSON, which `jq` parses.
   Because it is the raw body, fields the pydantic models deliberately
   ignore (`model_ftype`, `ui*`, `cors_proxy_enabled`, ...) show up in
   dumps.
2. **`metrics` is excluded** (user decision): it has no `--json`. Note its
   normal output is a *formatted report* parsed from the Prometheus
   exposition text, not the raw `# HELP`/`# TYPE` lines — if the raw
   exposition is ever wanted, it is a small follow-up.
3. **API shape: `raw: bool = False` keyword on `check_health`/`get_*`/
   `aget_*`** (the four commands above) — when true the function returns
   `(status: int, body: str)` instead of the model (union return type,
   e.g. `ModelList | tuple[int, str]`). This keeps each endpoint's
   param/timeout logic in its module (the CLI stays thin glue). The typed
   API path the user's async framework uses is unchanged (no `raw` → model).
4. **Exit codes in `--json` mode:** the CLI prints the body to stdout
   verbatim; `2xx` → exit 0, otherwise exit 1 (so `set -e` and `||` still
   work, and 503/501/400 error bodies are captured by pipes). Transport
   errors (connection/timeout) still raise `ServerError` → stderr, exit 1,
   nothing to print.
5. **jmespath: rejected/deferred.** `--json | jq` covers the shell porting
   path with no new dependency, and in Python the pydantic models already
   give typed field access (better than a string expression). Revisit only
   if the script port shows a real need (a `--field EXPR` option over the
   raw body, jmespath.py: pure Python, no deps, low-maintenance).
6. **`models [MODEL] --json` filters the raw body client-side** (added
   after initial review — the user's most common query): the parsed body's
   `data` is kept to entries whose `id` equals the model (exact, case-
   sensitive, same as the formatted view), and the result is re-emitted as
   JSON (`indent=2`) with the same `{"object": "list", "data": [...]}`
   envelope, so jq expressions work with or without the model. Filtering
   happens on the parsed dict, not the pydantic model, so unknown fields
   survive. No match → `models: no model with id '<query>'`, exit 1.
   Filtering applies to 2xx only; error bodies are printed raw.

## Code shape

- `server.py` — no change (`fetch`/`afetch` already return `(status, text)`).
- Per endpoint module (`health`/`models`/`props`/`slots`; `metrics`
  unchanged):

  ```python
  def get_models(server: str | None = None, raw: bool = False) -> "ModelList | tuple[int, str]":
      if raw:
          return fetch(resolve_server_url(server), "/v1/models")
      _, body = fetch_json(resolve_server_url(server), "/v1/models")
      return _models_from(body)
  ```

  i.e. raw mode just calls `fetch`/`afetch` (text, no JSON parsing, no
  validation) instead of `fetch_json`/`afetch_json`; the same params/timeout
  arguments are used, so `props --raw --autoload` still gets the 300 s read
  timeout. `aget_*` twins mirror this (the parity test guards the signature
  lockstep).

- `__main__.py` — `json: bool = typer.Option(False, help="Print the raw
  JSON response body instead of the formatted report.")` on the four
  commands (not `metrics`). In `--json` mode the CLI echoes the body
  verbatim (no `render()`) and exits 0 on 2xx, 1 otherwise:

  ```python
  if json:
      try:
          status, body = get_models(server, raw=True)
      except ServerError as err:
          typer.echo(f"models: {err}", err=True)
          raise typer.Exit(code=1) from err
      typer.echo(body)
      raise typer.Exit(code=0 if 200 <= status < 300 else 1)
  ```

  `models` additionally filters the raw body with the positional argument
  (2xx only): `_filter_models_json(body, model)` keeps `data` entries whose
  `id` equals the model, re-emits with `indent=2`; no match →
  `models: no model with id '<model>'` on stderr, exit 1.

## Safety note

`props --json` prints the full `chat_template` (raw Jinja2, ~27 KB) —
expected and wanted for dumping, but the flag help and SKILL.md must say so
explicitly. (This does not change the tool's normal behavior, which still
hides it.)

## Tests

- Per command (`health`/`models`/`props`/`slots`): `--json` prints the
  exact body text (assert the fixture text is present and the formatted
  report header, e.g. `models:`, is not).
- `props --json` output contains the fixture `chat_template` (the point of
  raw).
- Non-2xx `--json`: 503 JSON error body is printed, exit 1.
- `models MODEL --json`: filters to the exact-id entry (envelope kept,
  unknown fields preserved); no match → exit 1; 503 + model → raw error
  body, exit 1.
- API-level: `get_models(raw=True)` returns `(status, str)`; `aget_*`
  parity test passes unchanged (same `raw` kwarg on both).
- `FakeGet` records are unchanged (same URL/params/timeout as the model
  path).

## Doc sync

- `README.md` — mention `--json` (one line in the command section).
- `SKILL.md` — `--json` per command + the `props --json` chat_template
  warning; `--json | jq` example for script porting.
- `AGENTS.md` — conventions: `--json` mode semantics (body verbatim,
  2xx → 0).

## Verification

- `make test`
- live: `models --json | jq 'length'`, `models --json | jq '.data[0].id'`,
  `health --json`, `props Qwen3.8-27B --json | jq 'keys'` (keys only —
  never dump the whole props body), `slots Qwen3.8-27B --json | jq
  'length'`.

## Out of scope

- `--json` for `metrics` (raw Prometheus exposition text) — small follow-up
  if ever wanted.
- `--field` / jmespath expression evaluation — rejected for now; revisit
  only if the script port shows a real need.
- pretty-printing (`--json` re-serializing) — the server's own JSON is
  valid input for `jq`; pretty-printing can be `| jq .` if desired.
