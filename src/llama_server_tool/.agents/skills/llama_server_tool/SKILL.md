---
name: llama_server_tool
description: A greeter CLI (hello world) — greets someone by name. Use when asked to run llama_server_tool, greet someone, or adjust the greeting.
---

<!--
SPDX-License-Identifier: 0BSD
Copyright (c) 2026 llama-server-tool creators and contributors
-->

<!--
SPDX-License-Identifier: 0BSD
Copyright (c) 2026 llama_server_tool creators and contributors
-->

# llama_server_tool

A greeter CLI.

```
$ uv run llama_server_tool --name Broman --formal
Good day from llama_server_tool to Broman!
```

Two invocation paths: `uv run llama_server_tool ...` and `uv run python -m llama_server_tool ...`.
Run `uv run llama_server_tool --help` to see the options (`--name`, `--formal`).
