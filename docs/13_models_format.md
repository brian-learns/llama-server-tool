# Phase 13: `models` list format, filters, and show attributes

## Goal

Make `models` a pipe-friendly registry browser: a default output of quoted
ids (one per line), filters (`--loaded`, modalities), and opt-in table
columns (`--show-modalities`, `--show-meta` with selectable fields). This is
the user's "filter ideas" open item from AGENTS.md.

## User spec (approved direction)

```
$ llama-server-tool models            # one quoted id per line
"LiquidAI/LFM2-1.2B-Tool-GGUF:Q4_K_M"
"LiquidAI/LFM2.5-1.2B-Instruct-GGUF:BF16"
...

$ llama-server-tool models --loaded --input_modalities text --output_modalities text
"Qwen3.8-27B"

$ llama-server-tool models --loaded --show-meta
id n_params n_ctx_train n_embd n_vocab size vocab_type
"Qwen3.8-27B" 27.32B 262144 5120 248320 17.55GB true
```

Modalities come from each entry's `architecture.input_modalities` /
`architecture.output_modalities`; meta from the entry's `meta`.

## Live findings (router, build b10988)

- `architecture` is present on **every** registry entry (loaded and
  unloaded) — modality filters work without `--loaded`.
- `meta` is `null` for unloaded models, an object for loaded ones.
- This build's meta keys: `ftype` (str), `n_ctx`, `n_ctx_train`, `n_embd`,
  `n_params`, `n_vocab`, `size` (num), `vocab_type` (**bool** — `true`).
  Meta is build-dependent, so the model must not pin keys or types.
- The current `ModelMeta` (fixed required-int model) silently drops
  `ftype`/`n_ctx` and coerces `vocab_type: true` to `1`. It must go.
- Typer 0.27.2 cannot express an optional-value flag (`--show-meta [list]`
  as one option; probed: bare `--show-meta` → "requires an argument").

## Design

### Model changes (`models.py`)

- `ModelMeta` (class) → `ModelInfo.meta: dict[str, Any] | None`. No pinned
  keys or types; rendering is generic.
- New `ModelArchitecture` model: `input_modalities: list[str] = []`,
  `output_modalities: list[str] = []` (other keys ignored);
  `ModelInfo.architecture: ModelArchitecture | None = None`.
- `ModelList.select(loaded: bool = False, input_modalities=(),
  output_modalities=()) -> ModelList` — filtering, domain-side:
  - `--loaded`: keep entries with `status.value == "loaded"` (entries
    without `status` excluded).
  - modalities: a model matches a filter only if it has `architecture` and
    the corresponding list contains **every** requested modality (AND
    semantics — `--input_modalities text image` = accepts both).
  - order: registry order preserved (no sorting).
- `ModelList.render(show_modalities: bool = False, show_meta: bool = False,
  meta_fields: list[str] | None = None) -> str` — display modes:
  - default: `"<id>"` per line (double-quoted, paste-able; ids contain
    `/` and `:`). No header.
  - any show option: header row + one row per model, columns
    aligned to max width (space-separated; awk/cut-friendly):
    - `--show-modalities` → `input`, `output` columns, modalities
      comma-joined (`text,image`); missing architecture → blank cells.
    - `--show-meta` → one column per field, `meta_fields` order; bare
      `--show-meta` → default set `n_params n_ctx_train n_embd n_vocab
      size vocab_type` (the user's example). `--show-meta` implies
      `--loaded` (CLI-side).
    - cell formatting: `n_params` → `format_params` ("27.32B"), `size` →
      `format_bytes` ("17.55GB" — drop the current space), everything
      else via `format_value` (bools → `true`/`false`, strings verbatim).
      Missing key or null meta → blank cell.
  - single model (`models ID`) renders the same way: one row, header kept
    (consistent, `NR>1` scripts work).
  - unknown meta field (not present in any filtered model's meta) →
    `ValueError("unknown meta field 'X' (available: …)")`; CLI catches →
    stderr + exit 1.
  - empty result → empty string (no output), exit 0.
- Removed: `ModelMeta.render`, `ModelInfo.render`, `format_created`
  (vulture-checked; `created`/`owned_by`/`object` fields stay on
  `ModelInfo` — they're part of the documented API body; whitelist in
  vulture config only if flagged).
- `match()` (exact id) unchanged; CLI applies `match` → `select` → `render`.

### CLI (`__main__.py`)

New options on `models` (positional MODEL and `--server`/`--json` unchanged):

- `--loaded` (flag)
- `--input_modalities` / `--output_modalities` (repeatable, comma-split;
  free-form values — no enum, builds add modalities)
- `--show-modalities` (flag)
- `--show-meta` (flag; implies `--loaded`)
- `--meta-fields` (comma list; implies `--show-meta`; bare `--show-meta`
  = default set)

`--json` stays raw (only the existing MODEL client-side filter); the new
filters/show options are display-only and ignored with `--json`.

Exit codes: unchanged — 0 on success (incl. empty filter results), 1 on
server error / unknown meta field / MODEL given but absent from the
filtered set (existing `models: no model with id '<id>'`).

### Tests

- `select`: loaded-only; input AND (text+image matches only both);
  output; both combined; entry without architecture excluded by modality
  filters; registry order preserved; empty result.
- `render`: default quoted-id list; show-modalities columns (incl. blank
  for missing architecture); show-meta default set renders the user's
  example row verbatim (27.32B / 17.55GB / true); custom field order
  (`ftype,n_ctx`); blank cells for missing meta/key; `ValueError` on
  unknown field; single-entry row with header; empty → `""`.
- model parse: `architecture` (both lists); meta as dict with bool
  `vocab_type`, `ftype`, `n_ctx` (no coercion, no dropped keys).
- CLI: default id list; each filter/flag; `--meta-fields` implies
  `--show-meta`; `--show-meta` implies `--loaded`; MODEL + non-matching
  filter → exit 1; empty result → exit 0, empty stdout; `--json` ignores
  the new flags.
- Update existing tests asserting the old `models:\n  id: …` render.

### Docs

README (command table row + examples), SKILL.md models section, AGENTS.md
conventions (default quoted-id list; `select`/`render` split; meta is an
unpinned dict; modalities in `architecture`), close the "models output
filters" open item.

## Decisions (approved)

1. **Column spacing**: aligned columns (awk default-FS still works).
2. **AND vs OR** for multiple modalities: AND (model must support all
   requested).
3. **Flag shape**: `--show-meta` + companion `--meta-fields` (typer can't
   do an optional-value flag).
4. **`--json` + filters**: **error** (user decision) — `--json` cannot be
   combined with any of `--loaded`, `--input_modalities`,
   `--output_modalities`, `--show-modalities`, `--show-meta`,
   `--meta-fields`: `models: --json cannot be combined with --loaded, ...`
   (lists the flags actually given), exit 1. The existing `models MODEL
   --json` client-side filter stays.
5. **Empty filter result**: silent empty stdout, exit 0.
6. **Default meta set**: the six columns from the sample.

Extra rule from implementation: `--show-meta` with the *default* field set
is lenient (blank cells when no filtered model has meta yet, e.g. while a
model loads); an explicit `--meta-fields` is strict (unknown field →
error, since that's where typos live).

## Out of scope

- `--json` filtering by the new options (open question 4, follow-up).
- Substring/fuzzy id matching (positional stays exact), sorting, TSV.
- `architecture` fields beyond the two modality lists.
