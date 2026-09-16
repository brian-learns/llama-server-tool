# llama-server-tool

A command line tool to help administer a local llama-server

## initial layout 
stubs and templates
```
.
├── AGENTS.md               # from template
├── docs
│   └── 01_initial_plan.md  # this file
├── LICENSE
├── Makefile
├── pyproject.toml
├── README.md
├── scripts
│   └── test-all-versions.sh
├── src
│   └── llama_server_tool
│       ├── health.py       # Documentation stub
│       ├── __init__.py
│       ├── __main__.py
│       ├── metrics.py      # Documentation stub
│       ├── models.py       # Documentation stub
│       ├── props.py        # Documentation stub
│       └── py.typed
├── tests
│   └── test_greet.py
└── uv.lock
```
Documentation stub python files have sections of https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
as heredoc comments that have the documentation for the matching endpoint.

## initial phases

To start, we will do one command at a time

### health

```
llama-server-tool health  # returns a formated repoyyrt of server health from the endpoint
```

### models

```
llama-server-tool models  # returns a formated repoyyrt of server health from the endpoint
```

### props

** note ** this should default to not pre-loading the model

### Metrics


## Environment
 * uses `uv` to manage environment
 * uses `.envrc` to set .venv/bin into PATH
 * uses `make test` -- see `make` for more development targets
 * llama-server running on `http://127.0.0.0:8080/`


## Workflow
 * **Plan** write a planning document first
 * **Do** code after the user approves the plan
 * **Check** the user wants to check before git commit
 * **Act** commit the change after user approval
