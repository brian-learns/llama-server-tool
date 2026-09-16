# Phase 2: `models`

Plan for the second command: `llama-server-tool models`.

## CLI

```
llama-server-tool models [--server URL]
```

Same URL resolution as `health`: `--server` option → `LLAMA_SERVER_URL` env var →
default `http://127.0.0.0:8080`.

## Endpoint

`GET {server}/v1/models` (OpenAI-compatible model info API — see the docstring stub in
`models.py`). The response list always has exactly one element; `meta` can be `null`
(e.g. while the model is still loading).

## Shared extraction

Phase 1 promised to extract shared code when the second command lands. New module
`server.py` with:

- `DEFAULT_SERVER`, `REQUEST_TIMEOUT`, `resolve_server_url()` — moved out of `__main__.py`
- `ApiError` pydantic model: `{code: int, message: str, type: str}` — the standard
  llama-server error object (`health.py`'s `HealthError` is removed in its favor)
- `fetch_json(base: str, path: str) -> tuple[int, dict]` — does the `httpx.get`,
  raises `ServerError(message: str)` on connect/timeout/malformed JSON; returns the
  HTTP status code plus the parsed body

Both commands then follow the same thin shape:

```
base = resolve_server_url(server)
try: status, body = fetch_json(base, path)
except ServerError: stderr + exit 1
result = <Model>.model_validate(body)   # ValidationError → stderr + exit 1
echo(result.render())
exit 1 if result.error or status != 200
```

## Behavior

| Case | Output | Exit code |
|------|--------|-----------|
| `200` with `meta` | formatted report (below) | 0 |
| `200` with `meta: null` | report with `meta: (null — model may still be loading)` | 0 |
| error body (`{"error": {...}}`, e.g. 503) | `models: <message>` | 1 |
| connection error / timeout / bad JSON | detail to stderr | 1 |

## Code shape

- `models.py` — pydantic models own parsing + rendering:
  - `ModelMeta`: `vocab_type, n_vocab, n_ctx_train, n_embd, n_params, size` (ints)
  - `ModelInfo`: `id: str`, `object: str = "model"`, `created: int`, `owned_by: str`,
    `meta: ModelMeta | None`
  - `ModelList`: `object: str = "list"`, `data: list[ModelInfo]`, `error: ApiError | None`
  - `render()` produces:

    ```
    models:
      id:         ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
      created:    2024-12-25 15:57:03 UTC
      owned_by:   llamacpp
      meta:
        n_params:    8.03B
        n_ctx_train: 131072
        n_embd:      4096
        n_vocab:     128256
        size:        4.91 GB
        vocab_type:  2
    ```

  - human-readable helpers inside `models.py`: byte count → `GB`/`MB` (2 decimals),
    param count → `B`/`M` (e.g. `8.03B`); `created` → UTC timestamp string
- `__main__.py` — thin `models` command per the pattern above
- `health.py` — `Health.error` switches from `HealthError` to `server.ApiError`
  (no behavior change)

## Tests

`tests/test_models.py` (CLI via `CliRunner` + mocked `httpx.get`, model tests direct):

1. `200` with full `meta` → exit 0, expected report lines
2. `200` with `meta: null` → exit 0, null-meta line shown
3. `503` error body → exit 1, `models: <message>` on stdout
4. `httpx.ConnectError` → exit 1, stderr message
5. malformed JSON → exit 1, stderr message
6. `--server` override reaches the right URL
7. model rendering: with meta, without meta, error body
8. human-readable formatting: `8030261312 → 8.03B`, `4912898304 → 4.91 GB`,
   `512 → 512` (no unit), `created` timestamp

`tests/test_health.py` — adjust imports for `ApiError`; no behavior changes expected.

## Verification

- `make test`
- live: `uv run llama-server-tool models` against the server on `:8080`

## Out of scope for this phase

- `props`, `metrics` commands
- native `/models` endpoint, API key support, multiple models
