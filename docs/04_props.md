# Phase 3: `props`

Plan for the third command: `llama-server-tool props`.

## CLI

```
llama-server-tool props [--model ID] [--autoload]
```

- `--model` — model id to query properties for. When given, the request is
  `GET {server}/props?model=<id>&autoload=false`.
- `--autoload` — opt-in to `autoload=true`. **Default is `autoload=false`**: requesting
  props for a model with `autoload` on (or omitted) makes llama-server load the model
  into memory and pre-warm it, which we do not want by default.
- When `--model` is omitted: plain `GET {server}/props` (server global properties —
  no model param, nothing is loaded).
- `--server` / `LLAMA_SERVER_URL` / default as with the other commands.

## Safety constraint: never print the raw template

The `chat_template` field in the `/props` response is a raw Jinja2 system-prompt
template. Dumping it (or the raw JSON body) is not acceptable — large raw template
content has crashed agent sessions before. Therefore:

- `Model` captures `chat_template` (so validation passes) but `render()` **never emits
  its content** — it prints `chat_template: <hidden: N chars>` instead.
- The command never has a `--json`/raw-dump mode in this phase (or at all, unless
  asked later).
- No test fixture or live check may print the full props body; tests use small
  synthetic templates.

## Shared change

`server.fetch_json(base, path, params: dict[str, str] | None = None)` — pass `params`
through to `httpx.get(..., params=params)`; `None` keeps current behavior.
`health` and `models` are unaffected.

## Code shape

- `props.py` — pydantic models own parsing + rendering. All fields optional
  (`= None` / `= {}` / `= []`), extras ignored — server versions and the local
  registry-style server differ from the stub example:
  - `GenerationParams` — curated known params, all optional: `n_predict, seed,
    temperature, dynatemp_range, top_k, top_p, min_p, typical_p, repeat_last_n,
    repeat_penalty, presence_penalty, frequency_penalty, mirostat, mirostat_tau,
    mirostat_eta, stop (list[str]), max_tokens, n_keep, ignore_eos, stream,
    samplers (list[str])`
  - `DefaultGenerationSettings` — `id, n_ctx, speculative, is_processing,
    params: GenerationParams | None`
  - `Props`:
    - `default_generation_settings: DefaultGenerationSettings | None`
    - `total_slots: int | None`
    - `model_path: str | None`
    - `chat_template: str | None` (captured, never rendered)
    - `chat_template_caps: dict[str, Any] | None`
    - `modalities: dict[str, bool] | None`
    - `is_sleeping: bool | None`
    - `build_info: str | None`
    - `error: ApiError | None`
  - `render()` produces (only fields that are present are shown):

    ```
    props:
      model_path:          ../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
      total_slots:         1
      is_sleeping:         false
      modalities:          vision=false
      build_info:          b6909-abcdef
      chat_template:       <hidden: 12345 chars>
      generation settings:
        n_ctx:         1024
        speculative:   false
        params:
          temperature:       0.8
          top_k:             40
          top_p:             0.95
          min_p:             0.05
          ...
    ```

  - floats render rounded to 4 decimals (the server reports float32 artifacts like
    `0.800000011920929`); `None`/absent fields are omitted, not printed as `None`
- `__main__.py` — thin `props` command per the established pattern; builds
  `params = {"model": id, "autoload": "true"/"false"}` only when `--model` is given

## Behavior

| Case | Output | Exit code |
|------|--------|-----------|
| `200` props body | formatted report (template hidden) | 0 |
| error body (`{"error": {...}}`) | `props: <message>` | 1 |
| connection error / timeout / bad JSON | detail to stderr | 1 |

## Tests (`tests/test_props.py`)

CLI (via `CliRunner` + `FakeGet` from `tests/helpers.py`):

1. `200` sample body → exit 0, report lines shown; **`chat_template` content absent
   from output**, `<hidden: N chars>` line present
2. `--model foo` → URL `/props` with `model=foo&autoload=false` params
3. `--model foo --autoload` → `autoload=true`
4. no `--model` → no query params
5. `503` error body → exit 1, `props: <message>`
6. connection error → exit 1, stderr message

Model tests (direct):

7. full sample body renders; optional fields omitted when absent (empty `Props()`
   renders without crashing)
8. float rounding: `0.800000011920929 → 0.8`
9. `chat_template` of any length never appears in `render()` output

## Verification

- `make test`
- live: `uv run llama-server-tool props --model Qwen3.8-27B` (autoload=false by
  default) — output is the curated report only; never pipe or echo the raw curl
  response in the session.

## Out of scope for this phase

- `POST /props` (changing global properties)
- `metrics` command
- dumping the full params object, `--json` raw output
