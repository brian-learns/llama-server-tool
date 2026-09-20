# Phase 17: compact `status` board

## Goal

Make `status` much smaller in height **and** width — one line per process
(router + each loaded model), one tree line per slot — while keeping the
watch workflow (`watch -n 1 llama-server-tool status`) and the graceful
degradation of the collectors.

## New format

```
llama-server pid=237423 port=9931 rss=0.39GB virt=15.36GB vram=0.17GB
Qwen3.8-27B pid=237918 port=36039 rss=18.04GB virt=136.17GB vram=37.65GB
├─0 ␖ prompt=0 decoded=0 ctx=262144
├─1 ␖ prompt=0 decoded=0 ctx=262144
├─2 ⛭ prompt=76524 decoded=4238 ctx=262144
└─3 ␖ prompt=32734 decoded=0 ctx=262144
```

- **Process line**: `<name> pid=<pid> port=<port> rss=<g>GB virt=<g>GB
  vram=<g>GB` — the router first (`llama-server`), then one line per
  loaded model. Fields are omitted when unavailable (no `/proc`,
  no `nvidia-smi`, port not in `status.args`): e.g.
  `ModelB rss=1.20GB`. Memory keeps the 2-decimal GB format, space
  dropped (`0.39GB`).
- **Slot lines**: `├─<id> <state> prompt=<n> decoded=<n> ctx=<n>` —
  `├─` for all but the last slot, `└─` for the last. State glyph:
  `⛭` processing, `␖` idle (replaces `Status = IDLE/PROCESSING`).
  Values follow the slots.sh spec: `prompt` = `n_prompt_tokens // 0`,
  `decoded` = `next_token[0].n_decoded // 0` (guarded list/dict parse,
  the logic `_slot_line` already has), `ctx` = `n_ctx // 0`.
- **No `====` rules, no blank lines** between the process lines and
  blocks — the tree glyphs visually own the slots above them. A second
  model block simply continues: `ModelB pid=...` after Model A's `└─`.
- **slots error** (slots fetch failed for a loaded model): the slot tree
  is replaced by one line `└─ ! <message>`.
- `status: no loaded models`, the API-error line, and exit codes are
  unchanged.

Height: a 4-slot model block goes from 9 lines (+1 blank) to 5. Width:
the longest line goes from ~110 chars (slot line) / 57 (rule) to ~70
(model line).

## Decisions

- **Default changes in place, no flag** — `status` is the watch board;
  a `--compact` flag would split the tests and the docs for no user.
- **System footer stays verbatim** (`free -h` + the `nvidia-smi` gpu
  summary, one blank line before it, `--no-system` still omits it).
  Parsing `free`/`nvidia-smi` into one-liners is a follow-up: the
  external formats are the fragile part, and the footer is optional.
- **No digit alignment** within a block (the sketch aligns nothing);
  per-block column alignment and ANSI coloring are follow-ups.
- `state`/`host` remain stored-but-unrendered, as today.

## Changes

- `status.py`:
  - drop `RULE`;
  - `StatusBlock.render()` → process line (omit absent fields) +
    slot tree lines (new compact `_slot_line`);
  - `StatusReport.render()` joins server/blocks with `"\n"` (footer
    keeps the `"\n\n"` separator);
  - module docstring: the layout no longer "ports slots.sh" verbatim —
    it is the compact rewrite of it.
- `tests/test_status.py`: update the render expectations
  (`test_status_block_render_parity`, `test_status_block_render_variants`,
  `test_status_report_render`, `test_status_cli`); add a
  two-block render test (tree `├─`/`└─` across blocks) and an
  omitted-fields test (`StatusBlock(model="m")` → `m`).
- Docs: `status` section example in SKILL.md; README `status` row stays
  accurate (re-check wording); AGENTS.md unchanged beyond the render
  description if needed.

## Verification

- `make test`.
- Live (`:9931`, `Qwen3.8-27B` loaded): `status` and `status
  --no-system` render the compact board; `wc -l`/`awk '{print length}'`
  before/after to confirm the height/width drop; `status Qwen3.8-27B`
  focuses correctly; a busy slot (background generation) shows
  `⛭` with `decoded` incrementing under `watch -n 1`.

## Follow-ups (out of scope)

- Compact system footer (parse `free`/`nvidia-smi` into one-liners).
- Per-block column alignment for `prompt`/`decoded`/`ctx`.
- ANSI colors for processing slots / memory (old open item).
