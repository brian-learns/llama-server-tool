# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""
Composite `status` board: per-loaded-model memory and slot state, plus a
host-level system footer.

Compact rewrite of the slots.sh maintenance script layout: one line per
process (the `llama-server` router itself, port from the server URL, then
each loaded model: pid/port, rss/virt/vram) with a slot tree below each
(`⛭` processing, `␖` idle; prompt/decoded/ctx), and `free` + `nvidia-smi`
output at the bottom. Intended for `watch -n 1 llama-server-tool status`.

The registry (`/v1/models`) lists every loadable model; only entries with
`status.value == "loaded"` have a subprocess and are shown. The subprocess
port comes from `status.args` (`--port`), and the PID is found by scanning
`/proc/*/cmdline` (world-readable, so it works across accounts). The
`/proc` and `nvidia-smi` parts degrade silently when unavailable.
"""

import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel

from .models import get_models
from .server import ApiError, ServerError, resolve_server_url
from .slots import Slot, SlotNextToken, get_slots


def find_pids_by_ports(ports: set[int], proc_root: str = "/proc") -> dict[int, int]:
    """Map each port to the pid of the process launched with --port <port>."""
    found: dict[int, int] = {}
    if not ports:
        return found
    try:
        entries = [entry.name for entry in Path(proc_root).iterdir()]
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            args = [arg for arg in Path(proc_root, entry, "cmdline").read_bytes().split(b"\0") if arg]
        except OSError:
            continue
        for i, arg in enumerate(args):
            if arg == b"--port" and i + 1 < len(args) and args[i + 1].isdigit():
                port = int(args[i + 1])
                if port in ports and port not in found:
                    found[port] = int(entry)
    return found


def read_proc_mem(pid: int, proc_root: str = "/proc") -> tuple[float, float] | None:
    """Return (rss_gb, vsz_gb) for a pid from /proc/<pid>/status, or None."""
    try:
        text = Path(proc_root, str(pid), "status").read_text(encoding="utf-8")
    except OSError:
        return None
    rss_kb = vsz_kb = None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            rss_kb = int(line.split()[1])
        elif line.startswith("VmSize:"):
            vsz_kb = int(line.split()[1])
    if rss_kb is None or vsz_kb is None:
        return None
    return rss_kb / 1024 / 1024, vsz_kb / 1024 / 1024


def nvidia_vram_by_pid(timeout: float = 5.0) -> dict[int, float]:
    """Map pid -> VRAM in GB for all compute apps, or {} when unavailable."""
    try:
        # fixed PATH binary, no user input
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    vram: dict[int, float] = {}
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            vram[int(parts[0])] = int(parts[1]) / 1024
    return vram


def system_footer(timeout: float = 5.0) -> str:
    """The host-level footer: `free -h` and an nvidia-smi gpu summary, verbatim."""
    sections: list[str] = []
    argvs = (
        ["free", "-h"],
        ["nvidia-smi", "--query-gpu=clocks.current.graphics,power.draw,temperature.gpu", "--format=csv,noheader"],
    )
    for argv in argvs:
        try:
            # fixed argv from a literal tuple; no user input
            result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            sections.append(result.stdout.rstrip("\n"))
    return "\n".join(sections)


class StatusBlock(BaseModel):
    """One loaded model: identity, OS memory, and slot state."""

    model: str
    state: str | None = None
    port: int | None = None
    host: str | None = None
    pid: int | None = None
    rss_gb: float | None = None
    vsz_gb: float | None = None
    vram_gb: float | None = None
    slots: list[Slot] = []
    slots_error: str | None = None

    @staticmethod
    def _slot_line(slot: Slot) -> str:
        """Format the compact slot values: state glyph plus prompt/decoded/ctx (0 when absent)."""
        state = "⛭" if slot.is_processing else "␖"
        prompt = slot.n_prompt_tokens or 0
        token = slot.next_token
        if isinstance(token, list):
            first = token[0] if token else None
            decoded = first.n_decoded if first is not None and first.n_decoded is not None else 0
        elif isinstance(token, SlotNextToken):
            decoded = token.n_decoded or 0
        else:
            decoded = 0
        ctx = slot.n_ctx or 0
        return f"{state} prompt={prompt} decoded={decoded} ctx={ctx}"

    def render(self) -> str:
        """Format the process line and its slot tree for output."""
        line = self.model
        if self.pid is not None:
            line += f" pid={self.pid}"
        if self.port is not None:
            line += f" port={self.port}"
        if self.rss_gb is not None:
            line += f" rss={self.rss_gb:.2f}GB"
        if self.vsz_gb is not None:
            line += f" virt={self.vsz_gb:.2f}GB"
        if self.vram_gb is not None:
            line += f" vram={self.vram_gb:.2f}GB"
        lines = [line]
        if self.slots_error is not None:
            lines.append(f"└─ ! {self.slots_error}")
        for i, slot in enumerate(self.slots):
            branch = "└─" if i == len(self.slots) - 1 else "├─"
            lines.append(f"{branch}{slot.id} {self._slot_line(slot)}")
        return "\n".join(lines)


class StatusReport(BaseModel):
    """The full status board: server header, one block per loaded model, plus the system footer."""

    blocks: list[StatusBlock] = []
    server: StatusBlock | None = None
    error: ApiError | None = None
    system: str | None = None

    def render(self) -> str:
        """Format the board for output: the process lines are contiguous, the footer is set off."""
        if self.error is not None:
            return f"status: {self.error.message}"
        parts = []
        if self.server is not None:
            parts.append(self.server.render())
        if self.blocks:
            parts.extend(block.render() for block in self.blocks)
        else:
            parts.append("status: no loaded models")
        body = "\n".join(parts)
        if self.system:
            body += f"\n\n{self.system}"
        return body


def get_status(server: str | None = None, model: str | None = None, include_system: bool = True) -> StatusReport:
    """Build the status board: server header, one block per loaded model, plus the system footer."""
    registry = get_models(server)
    if registry.error is not None:
        return StatusReport(error=registry.error)
    loaded = [info for info in registry.data if info.status is not None and info.status.value == "loaded"]
    if model is not None:
        loaded = [info for info in loaded if info.id == model]
    # the router's own port is the server URL's port (8080 when the URL omits one)
    router_port = urlsplit(resolve_server_url(server)).port or 8080
    ports: set[int] = {router_port}
    for info in loaded:
        if info.status is not None and info.status.port is not None:
            ports.add(info.status.port)
    pids = find_pids_by_ports(ports)
    vram = nvidia_vram_by_pid() if pids else {}
    server_pid = pids.get(router_port)
    server_mem = read_proc_mem(server_pid) if server_pid is not None else None
    server_block = StatusBlock(
        model="llama-server",
        port=router_port,
        pid=server_pid,
        rss_gb=server_mem[0] if server_mem is not None else None,
        vsz_gb=server_mem[1] if server_mem is not None else None,
        vram_gb=vram.get(server_pid) if server_pid is not None else None,
    )
    blocks: list[StatusBlock] = []
    for info in loaded:
        status = info.status
        port = status.port if status is not None else None
        pid = pids.get(port) if port is not None else None
        mem = read_proc_mem(pid) if pid is not None else None
        block = StatusBlock(
            model=info.id,
            state=status.value if status is not None else None,
            port=port,
            host=status.host if status is not None else None,
            pid=pid,
            rss_gb=mem[0] if mem is not None else None,
            vsz_gb=mem[1] if mem is not None else None,
            vram_gb=vram.get(pid) if pid is not None else None,
        )
        try:
            slots_report = get_slots(server, model=info.id)
        except ServerError as err:
            block.slots_error = str(err)
        else:
            if slots_report.error is not None:
                block.slots_error = slots_report.error.message
            else:
                block.slots = slots_report.slots
        blocks.append(block)
    system = system_footer() if include_system else ""
    return StatusReport(server=server_block, blocks=blocks, system=system or None)
