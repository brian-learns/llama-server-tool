# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Tests for the status command (CLI) and the StatusReport/StatusBlock models."""

import subprocess

import pytest
from typer.testing import CliRunner

import llama_server_tool.status as status_module
from llama_server_tool.__main__ import app
from llama_server_tool.models import ModelInfo, ModelList, ModelStatus
from llama_server_tool.server import ServerError
from llama_server_tool.slots import Slot, SlotNextToken, SlotsReport
from llama_server_tool.status import (
    StatusBlock,
    StatusReport,
    find_pids_by_ports,
    nvidia_vram_by_pid,
    read_proc_mem,
    system_footer,
)

runner = CliRunner()

LOADED_BODY = {
    "object": "list",
    "data": [
        {
            "id": "Qwen3.8-27B",
            "object": "model",
            "created": 1789669522,
            "owned_by": "llamacpp",
            "status": {
                "value": "loaded",
                "args": ["llama-server", "--alias", "Qwen3.8-27B", "--host", "127.0.0.1", "--port", "48249", "--metrics"],
            },
        },
        {
            "id": "Ornith-1.0-9B",
            "object": "model",
            "created": 1789669522,
            "owned_by": "llamacpp",
            "status": {"value": "unloaded", "args": []},
        },
    ],
}

SLOTS_BODY = [
    {"id": 0, "n_ctx": 262144, "speculative": True, "is_processing": False},
    {
        "id": 3,
        "n_ctx": 262144,
        "speculative": True,
        "is_processing": True,
        "id_task": 0,
        "n_prompt_tokens": 4433,
        "n_prompt_tokens_processed": 4096,
        "n_prompt_tokens_cache": 0,
        "next_token": [{"has_next_token": True, "has_new_line": False, "n_remain": -1, "n_decoded": 0}],
    },
]


def make_proc(root, pids):
    """Create fake /proc entries: pid -> (cmdline args, status text)."""
    for pid, (cmdline, status_text) in pids.items():
        entry = root / str(pid)
        entry.mkdir(parents=True)
        (entry / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in cmdline) + b"\0")
        (entry / "status").write_text(status_text)
    return root


class FakeRun:
    """Stand-in for subprocess.run keyed on argv[0]."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        return self.results[argv[0]]


def completed(returncode, stdout):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def fake_status_env(monkeypatch, footer="MEM FOOTER"):
    """Point status_module at canned registry/slots/OS data."""
    monkeypatch.setattr(status_module, "get_models", lambda server=None: ModelList.model_validate(LOADED_BODY))
    monkeypatch.setattr(
        status_module,
        "get_slots",
        lambda server=None, model=None: SlotsReport(model_name=model, slots=[Slot.model_validate(s) for s in SLOTS_BODY]),
    )
    monkeypatch.setattr(status_module, "find_pids_by_ports", lambda ports, proc_root="/proc": {})
    monkeypatch.setattr(status_module, "nvidia_vram_by_pid", lambda timeout=5.0: {})
    monkeypatch.setattr(status_module, "system_footer", lambda timeout=5.0: footer)


def test_model_status_parses_port_and_host():
    ms = ModelStatus.model_validate(
        {"value": "loaded", "args": ["llama-server", "--host", "127.0.0.1", "--port", "48249"]}
    )
    assert ms.port == 48249
    assert ms.host == "127.0.0.1"


def test_model_status_missing_flags():
    ms = ModelStatus.model_validate({"value": "unloaded", "args": []})
    assert ms.port is None
    assert ms.host is None


def test_model_info_without_status():
    info = ModelInfo.model_validate(
        {"id": "m.gguf", "created": 1735142223, "owned_by": "llamacpp", "meta": None}
    )
    assert info.status is None


def test_find_pids_by_ports(tmp_path):
    root = make_proc(
        tmp_path,
        {
            "111": (["llama-server", "--port", "48249"], "Name: llama-server\n"),
            "222": (["bash", "-c", "sleep"], "Name: bash\n"),
            "333": (["llama-server", "--port", "55555"], "Name: llama-server\n"),
        },
    )
    assert find_pids_by_ports({48249}, proc_root=str(root)) == {48249: 111}
    assert find_pids_by_ports(set(), proc_root=str(root)) == {}


def test_find_pids_by_ports_missing_proc(tmp_path):
    assert find_pids_by_ports({48249}, proc_root=str(tmp_path / "nope")) == {}


def test_read_proc_mem(tmp_path):
    root = make_proc(tmp_path, {"111": ([], "Name: llama-server\nVmRSS: 2048000 kB\nVmSize: 134217728 kB\n")})
    rss, vsz = read_proc_mem(111, proc_root=str(root))
    assert (rss, vsz) == (pytest.approx(1.953125), pytest.approx(128.0))


def test_read_proc_mem_missing(tmp_path):
    assert read_proc_mem(999, proc_root=str(tmp_path)) is None


def test_nvidia_vram_by_pid(monkeypatch):
    fake = FakeRun({"nvidia-smi": completed(0, "342265, 38554\n999, 1024\n")})
    monkeypatch.setattr(status_module.subprocess, "run", fake)
    vram = nvidia_vram_by_pid()
    assert vram == {342265: pytest.approx(37.650390625), 999: pytest.approx(1.0)}


def test_nvidia_vram_by_pid_unavailable(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(status_module.subprocess, "run", boom)
    assert nvidia_vram_by_pid() == {}


def test_nvidia_vram_by_pid_nonzero(monkeypatch):
    monkeypatch.setattr(status_module.subprocess, "run", FakeRun({"nvidia-smi": completed(9, "")}))
    assert nvidia_vram_by_pid() == {}


def test_system_footer(monkeypatch):
    fake = FakeRun(
        {
            "free": completed(0, "               total        used\nMem:            62Gi        41Gi\n"),
            "nvidia-smi": completed(0, "1500 MHz, 245.31 W, 42 °C\n"),
        }
    )
    monkeypatch.setattr(status_module.subprocess, "run", fake)
    assert system_footer() == "               total        used\nMem:            62Gi        41Gi\n1500 MHz, 245.31 W, 42 °C"


def test_system_footer_skips_missing(monkeypatch):
    def free_ok(argv, **kwargs):
        if argv[0] == "free":
            return completed(0, "Mem: ok\n")
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(status_module.subprocess, "run", free_ok)
    assert system_footer() == "Mem: ok"


def test_status_block_render_parity():
    block = StatusBlock(
        model="Qwen3.8-27B",
        state="loaded",
        port=48249,
        host="127.0.0.1",
        pid=342265,
        rss_gb=21.71,
        vsz_gb=139.87,
        vram_gb=37.65,
        slots=[
            Slot(id=0, n_ctx=262144, speculative=True, is_processing=False),
            Slot(
                id=3,
                n_ctx=262144,
                speculative=True,
                is_processing=True,
                n_prompt_tokens=165811,
                next_token=[SlotNextToken(has_next_token=False, has_new_line=False, n_remain=-1, n_decoded=0)],
            ),
        ],
    )
    expected = "\n".join(
        [
            "Qwen3.8-27B pid=342265 port=48249 rss=21.71GB virt=139.87GB vram=37.65GB",
            "├─0 ␖ prompt=0 decoded=0 ctx=262144",
            "└─3 ⛭ prompt=165811 decoded=0 ctx=262144",
        ]
    )
    assert block.render() == expected


def test_status_block_render_variants():
    # absent fields are omitted from the process line
    assert StatusBlock(model="m").render() == "m"
    assert StatusBlock(model="Qwen3.8-27B", port=48249).render() == "Qwen3.8-27B port=48249"
    assert "vram" not in StatusBlock(model="m", rss_gb=1.0, vsz_gb=2.0).render()
    # dict-form next_token (some builds) still yields its n_decoded
    slot = Slot(id=1, is_processing=True, n_ctx=8, next_token=SlotNextToken(n_decoded=5))
    assert "decoded=5" in StatusBlock(model="m", slots=[slot]).render()
    assert "└─ ! boom" in StatusBlock(model="m", slots_error="boom").render()


def test_status_report_render():
    server = StatusBlock(model="llama-server", port=8080)
    block = StatusBlock(model="m", port=1)
    assert StatusReport(server=server, blocks=[block], system="FOOTER").render() == (
        server.render() + "\n" + block.render() + "\n\nFOOTER"
    )
    assert StatusReport(server=server).render() == server.render() + "\nstatus: no loaded models"
    assert StatusReport().render() == "status: no loaded models"
    assert (
        StatusReport(error=ModelList.model_validate({"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}).error).render()
        == "status: Loading model"
    )


def test_status_render_two_blocks():
    """Each block owns its slot tree; the branch glyphs reset per block."""
    a = StatusBlock(model="A", slots=[Slot(id=0), Slot(id=1)])
    b = StatusBlock(model="B", slots=[Slot(id=0), Slot(id=1)])
    idle = "␖ prompt=0 decoded=0 ctx=0"
    assert StatusReport(blocks=[a, b]).render() == (
        f"A\n├─0 {idle}\n└─1 {idle}\nB\n├─0 {idle}\n└─1 {idle}"
    )


def test_get_status_composition(monkeypatch):
    fake_status_env(monkeypatch)
    seen_ports = []
    monkeypatch.setattr(
        status_module,
        "find_pids_by_ports",
        lambda ports, proc_root="/proc": seen_ports.append(set(ports)) or {8080: 111, 48249: 342265},
    )
    mems = {111: (0.39, 15.36), 342265: (21.71, 139.87)}
    monkeypatch.setattr(status_module, "read_proc_mem", lambda pid, proc_root="/proc": mems[pid])
    monkeypatch.setattr(status_module, "nvidia_vram_by_pid", lambda timeout=5.0: {111: 0.17, 342265: 37.65})
    report = status_module.get_status()
    assert seen_ports == [{8080, 48249}]  # router port (from default URL) + subprocess port
    assert report.server.model == "llama-server"
    assert (report.server.pid, report.server.port) == (111, 8080)
    assert (report.server.rss_gb, report.server.vsz_gb, report.server.vram_gb) == (0.39, 15.36, 0.17)
    assert [b.model for b in report.blocks] == ["Qwen3.8-27B"]  # unloaded model never shown
    block = report.blocks[0]
    assert (block.pid, block.port, block.host) == (342265, 48249, "127.0.0.1")
    assert (block.rss_gb, block.vsz_gb, block.vram_gb) == (21.71, 139.87, 37.65)
    assert [s.id for s in block.slots] == [0, 3]
    assert report.system == "MEM FOOTER"


def test_get_status_router_port_from_url(monkeypatch):
    fake_status_env(monkeypatch)
    monkeypatch.setattr(status_module, "find_pids_by_ports", lambda ports, proc_root="/proc": {9931: 404576})
    monkeypatch.setattr(status_module, "read_proc_mem", lambda pid, proc_root="/proc": (0.39, 15.36))
    report = status_module.get_status(server="http://127.0.0.1:9931")
    assert (report.server.pid, report.server.port) == (404576, 9931)
    monkeypatch.setattr(status_module, "read_proc_mem", lambda pid, proc_root="/proc": None)
    report = status_module.get_status(server="http://127.0.0.1")  # URL without port: llama-server default
    assert (report.server.pid, report.server.port) == (None, 8080)


def test_get_status_model_filter_and_no_system(monkeypatch):
    calls = []
    fake_status_env(monkeypatch, footer="")
    monkeypatch.setattr(
        status_module,
        "get_slots",
        lambda server=None, model=None: calls.append(model) or SlotsReport(slots=[]),
    )
    assert [b.model for b in status_module.get_status(model="Qwen3.8-27B").blocks] == ["Qwen3.8-27B"]
    assert calls == ["Qwen3.8-27B"]
    calls.clear()
    assert status_module.get_status(model="Ornith-1.0-9B").blocks == []  # unloaded: never queried
    assert calls == []


def test_get_status_registry_error(monkeypatch):
    body = {"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}
    monkeypatch.setattr(status_module, "get_models", lambda server=None: ModelList.model_validate(body))
    report = status_module.get_status()
    assert report.error is not None
    assert report.render() == "status: Loading model"


def test_status_cli(monkeypatch):
    fake_status_env(monkeypatch)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "llama-server port=8080" in result.output
    assert result.output.index("llama-server port=8080") < result.output.index("Qwen3.8-27B port=48249")
    assert "Qwen3.8-27B port=48249" in result.output
    assert "└─3 ⛭ prompt=4433 decoded=0 ctx=262144" in result.output
    assert "MEM FOOTER" in result.output


def test_status_cli_no_system(monkeypatch):
    fake_status_env(monkeypatch)
    result = runner.invoke(app, ["status", "--no-system"])
    assert result.exit_code == 0
    assert "MEM FOOTER" not in result.output


def test_status_cli_model_filter(monkeypatch):
    fake_status_env(monkeypatch)
    result = runner.invoke(app, ["status", "Ornith-1.0-9B"])
    assert result.exit_code == 1
    assert "status: no loaded model with id 'Ornith-1.0-9B'" in result.stderr


def test_status_cli_server_down(monkeypatch):
    def boom(server=None):
        raise ServerError("connection refused")

    monkeypatch.setattr(status_module, "get_models", boom)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "status: connection refused" in result.stderr
