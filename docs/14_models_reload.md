# Phase 14: `models --reload` (trigger `GET /v1/models?reload=1`)

## Goal

Stop restarting llama-server after downloading new models: `models --reload`
triggers the server's registry refresh and prints the refreshed list.

## Endpoint (from the llama.cpp server docs, quoted by the user)

`GET /v1/models?reload=1` refreshes the model list from the source
(`--models-dir`, `/home/avramick/models` on the dev router):

- a running model updated or removed from the source **is unloaded**;
- a non-running model is added or updated according to the source.

The response is the normal `/v1/models` body (the refreshed list).

This is the only endpoint this tool uses that mutates server state.

## Design (approved; implemented and verified live)

Live verification: `models --reload --loaded` kept the loaded set
unchanged (no source changes on disk) and the freshly downloaded
`Nemotron-3.5-Lightning` model appeared in the registry (40 → 41 entries)
in ~0.2 s. Source check (`src/tools/server/server-models.cpp`,
`get_router_models`): any non-empty `reload` param → `load_models()`;
reload never spawns an instance (nothing is loaded).

- **Flag, not command**: `models --reload`. Same endpoint/body/output as
  `models`; composes with every other option (`--loaded`, modalities,
  `--show-meta`, `--json`). No interactive confirmation (script/watch
  usage); the unload semantics live in the help text and docs.
- **API**: `get_models(server, raw=False, reload=False)` and
  `aget_models(...)` — `reload=True` sends `params={"reload": "1"}` on
  both the model and raw paths. `raw` overloads gain `reload: bool = False`
  (keyword-only, as before).
- **CLI**: `--reload` passes through to both paths; it is *not* part of
  the `--json` conflict check (request parameter, not display filter —
  `models --json --reload` is valid).
- Help text: state the mutation explicitly, e.g.
  "Refresh the model list from the models dir first (loaded models whose
  source was updated or removed will be unloaded)."

## Tests

- API: `FakeGet` records `params` — `get_models(reload=True)` →
  `{"reload": "1"}`; default → `None`. Same for `aget_models` (async
  parity).
- CLI: `models --reload` → params recorded, id list output;
  `models --json --reload` → raw body + params; `models --reload --loaded`
  → filter applied to the refreshed list; `--json` conflict check
  unchanged.

## Verification

- `make test`.
- Live (careful — mutating): snapshot the loaded set
  (`models --loaded --json | jq ...`), run `models --reload`, re-snapshot;
  the loaded set must be unchanged (no model files changed on disk), and
  the registry should now include any models downloaded since the last
  restart.

## Docs

README (models row/paragraph), SKILL.md, AGENTS.md (conventions + a gotcha:
`models --reload` is the one mutating endpoint — it can unload running
models whose source changed or disappeared).

## Out of scope

- `--timeout` on `models` (default 5 s read applies; add only if a reload
  ever times out on a slow/network models dir).
- Watching/polling reloads; a dedicated `reload` command.
