# Phase 12: `status` — a watch-friendly server board

Port `~/llama/llama_cpp/slots.sh` into a new `status` command: for each
loaded model, a block with port + per-model memory + one line per slot,
followed by a host-level system footer. The goal is
`watch -n 1 llama-server-tool status` as a poor man's top for models.

## slots.sh parity (the spec)

```
=================================================================
Qwen3.8-27B (PID: 342265 | Port: 48249)
 -> Unified System RAM (RSS): 1.95 GB
 -> Virtual Memory Footprint: 119.31 GB
 -> Dedicated Blackwell VRAM: 37.64 GB
 -> Slot [0]: Status = IDLE | Context Ingested = 0 tokens | Active Gen Tokens = 0 | n_ctx = 262144
 -> Slot [3]: Status = PROCESSING | Context Ingested = 4096 tokens | Active Gen Tokens = 0 | n_ctx = 262144
=================================================================
<free -mh output>
<nvidia-smi clocks/power/temp csv output>
```

Field mapping (confirmed from the script's jq lines):

| slots.sh piece | source |
| -------------- | ------ |
| model, port, host | `/v1/models` registry `status.args` (`--port`/`--host` + next value) |
| loaded/unloaded | registry `status.value` (`loaded` / `unloaded`, verified live) |
| PID | `/proc/*/cmdline` scan for `--port <port>` (world-readable; replaces the script's `systemd-cgls --user`, which is why it needed the same account) |
| RSS / VSZ | `/proc/<pid>/status` `VmRSS` / `VmSize` (kB → GB, 2 decimals) |
| VRAM | one `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits` per invocation, mapped by pid (MiB → GB) |
| Status | `/slots` `is_processing` → `PROCESSING` / `IDLE` |
| Context Ingested | `/slots` `n_prompt_tokens // 0` (new field on `Slot`) |
| Active Gen Tokens | `/slots` `next_token[0].n_decoded // 0` (dict-or-list handling we already have) |
| n_ctx | `/slots` `n_ctx // 0` |
| footer | `free -h` + `nvidia-smi --query-gpu=clocks.current.graphics,power.draw,temperature.gpu --format=csv,noheader`, verbatim |

## Decisions (for confirmation)

1. **Name: `status`** (a board, not a top-N sort; rename is trivial if
   `top-models` wins). Takes an optional positional `MODEL` (exact id, same
   semantics as the other commands) to show one block only.
2. **Scope: actively-run models only** (confirmed). One `/v1/models`
   fetch; `/slots?model=<id>` (through the router, via the existing
   `get_slots`) only for models with `status.value == "loaded"`. The
   registry lists every loadable GGUF in the HF cache (~40) — the board
   shows only what is running; the full registry is the `models`
   command's job. No `--all`.
3. **Memory lines are in** (confirmed): RSS/VSZ/VRAM per loaded model, with
   cross-account PID discovery by scanning `/proc/*/cmdline` once per
   invocation (port → pid map). No PID found → memory lines skipped
   silently. `/proc` is Linux-only: on other platforms the memory section is
   skipped, everything else works. VRAM: `nvidia-smi` missing or failing →
   VRAM line skipped; present but no entry for the pid →
   `[No active VRAM allocation detected]` (slots.sh parity). Labels keep
   the script's wording ("Unified System RAM (RSS)", "Virtual Memory
   Footprint", "Dedicated Blackwell VRAM") for familiarity.
4. **System footer on by default; `--no-system` disables it.** Runs
   `free -h` and the `nvidia-smi` gpu query as fixed-argv subprocesses
   (no shell, 5 s timeout each), prints stdout verbatim. Missing binary,
   non-zero exit, or timeout → section skipped *silently* so watch output
   stays the same size every tick.
5. **No ANSI color in phase 12** (slots.sh red/greens PROCESSING/IDLE).
   Under `watch` stdout is a pipe, so TTY detection would disable color in
   exactly the main use case; always-on escapes would pollute captured
   output and tests. Plain text now, color as a possible follow-up with a
   `--no-color` escape.
6. **Sync-only API** this phase: `get_status(...)` composes
   `get_models()` + `get_slots()` + OS collectors; no `aget_status` twin
   (the board is a human-facing view, not a data-injection path). Revisit
   if the async framework ever wants it.
7. **Exit codes:** board rendered (including all-busy or all-idle states)
   → 0; server unreachable / unusable registry → stderr + 1 (standard
   `ServerError` path).

## Code shape

- `models.py` — `ModelInfo` gains `status: ModelStatus | None = None`:

  ```python
  class ModelStatus(BaseModel):
      """Router-mode registry entry status (value + subprocess launch args)."""
      value: str | None = None
      args: list[str] = []

      @property
      def port(self) -> int | None: ...   # args after --port
      @property
      def host(self) -> str | None: ...   # args after --host
  ```

  `render()` untouched; non-router servers (no `status` field) keep working
  (None → header without port, no memory section).
- `slots.py` — `Slot` gains `n_prompt_tokens: int | None = None`;
  `Slot.render()` untouched (the board renders its own slot line).
- **New module `status.py`** (composite command — not an endpoint, so it
  composes existing API functions; keeps the per-endpoint layering intact):

  ```python
  class StatusBlock(BaseModel):
      model: str
      state: str | None            # registry status.value
      port: int | None
      host: str | None
      pid: int | None
      rss_gb: float | None
      vsz_gb: float | None
      vram_gb: float | None
      slots: list[Slot] = []
      def render(self) -> str: ...  # the === block

  class StatusReport(BaseModel):
      blocks: list[StatusBlock]
      error: ApiError | None = None   # registry error body, if any
      system: str | None = None       # footer text, already formatted
      def render(self) -> str: ...

  def get_status(server: str | None = None, model: str | None = None,
                 include_system: bool = True) -> StatusReport: ...
  ```

  OS collectors, each independently testable:

  ```python
  def find_pids_by_ports(ports: set[int], proc_root: str = "/proc") -> dict[int, int]: ...
  def read_proc_mem(pid: int, proc_root: str = "/proc") -> tuple[float, float] | None: ...  # rss_gb, vsz_gb
  def nvidia_vram_by_pid(timeout: float = 5.0) -> dict[int, float]: ...  # pid -> GB
  def system_footer(timeout: float = 5.0) -> str: ...  # free -h + nvidia-smi, verbatim, silent skips
  ```

  - `find_pids_by_ports` scans once per invocation; cmdline is NUL-separated.
  - `nvidia_vram_by_pid` runs nvidia-smi **once** (the script ran it per
    pid); empty dict when unavailable.
  - `system_footer` / `nvidia_vram_by_pid` take the timeout so tests can
    use tiny values; subprocess calls are fixed-argv, `# noqa: S603` with
    the reason.
- `__main__.py` — `status` command (thin glue):

  ```python
  @app.command()
  def status(
      model: str | None = typer.Argument(None, help="Model id to show (exact match)."),
      server: str | None = typer.Option(None, help="Base URL of the llama-server."),
      no_system: bool = typer.Option(False, "--no-system", help="Omit the free/nvidia-smi footer."),
  ) -> None:
      """Show a watch-friendly board: per-model memory and slot state."""
  ```

## Tests

- `ModelStatus.port`/`host`: parsed from args; absent flags → None;
  `ModelInfo` without `status` still validates (non-router body).
- OS collectors with `tmp_path` fake proc trees (cmdline with/without
  `--port`, VmRSS/VmSize files, missing pid) and monkeypatched
  `subprocess.run` (happy path, `FileNotFoundError`, non-zero exit,
  `TimeoutExpired`) — no real /proc, no nvidia dependency.
- `get_status` composition with monkeypatched `get_models`/`get_slots`
  (module-level): one `/slots` call per *loaded* model only (unloaded
  models are never queried); `model=` filter fetches only that model's
  slots; registry error body → `StatusReport.error` set.
- Render: exact block layout against a fixture (parity with the spec
  above), PID-less header variant, no-VRAM variant, footer appended once,
  no-loaded-models line, per-model slots-failure line.
- CLI: full board with fakes (exit 0); `--no-system` omits footer; `MODEL`
  filter; server down → exit 1 + stderr.
- `Slot.n_prompt_tokens`: present in a busy fixture, absent otherwise
  (None); existing slot tests unchanged.

## Doc sync

- `README.md` — command table row + one line on `--no-system`.
- `SKILL.md` — new `status` section with an example block and the
  `watch -n 1` usage.
- `AGENTS.md` —
  - command list gains `status`;
  - **retire the open item** "Router-mode subprocess ports are not exposed
    by the API" — they are, via `/v1/models` `status.args` (build b10988+);
  - conventions: composite commands live in their own module composing the
    endpoint APIs; OS collectors take `proc_root`/timeout parameters so
    tests never touch the real host; `/proc` and nvidia-smi are
    Linux/GPU-optional and must degrade silently.

## Verification

- `make test`
- live (router, `LLAMA_SERVER_URL=http://127.0.0.1:9931`):
  - `uv run llama-server-tool status` — Qwen3.8-27B block with port 48249,
    memory lines (PID found via /proc scan from this account), 4 slot
    lines, footer;
  - `status --no-system`, `status Qwen3.8-27B`;
  - side-by-side with `slots.sh` run in the avramick account (visual diff);
  - `watch -n 1 uv run llama-server-tool status` for a minute.
- open: confirm `n_prompt_tokens` appears on a *busy* slot through the
  router (idle slots omit it; the mapping is taken from slots.sh's jq, but
  a live busy slot is the proof) — user pastes
  `slots Qwen3.8-27B --json | jq '.[0] | del(.params)'` while busy.

## Out of scope

- ANSI color for PROCESSING/IDLE (the watch/pipe nuance) — follow-up with
  a `--no-color` escape.
- `aget_status` async twin.
- standalone `system` command (trivial addition later — the footer is a
  function already).
- per-slot `params` rendering (separate open item).
- polling `unloaded` models' slots; non-Linux memory collection.
