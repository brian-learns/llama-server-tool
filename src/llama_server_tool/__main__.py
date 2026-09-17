# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Command line tool to administer a local llama-server."""

import typer

from .health import check_health
from .metrics import get_metrics
from .models import get_models
from .props import get_props
from .server import ServerError
from .slots import get_slots

app = typer.Typer()


# The explicit callback prints the command list when no subcommand is given.
@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Administer a local llama-server."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def health(server: str | None = typer.Option(None, help="Base URL of the llama-server.")) -> None:
    """Check server health via GET /health."""
    try:
        result = check_health(server)
    except ServerError as err:
        typer.echo(f"health: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None or result.status != "ok":
        raise typer.Exit(code=1)


@app.command()
def models(server: str | None = typer.Option(None, help="Base URL of the llama-server.")) -> None:
    """Show the loaded model via GET /v1/models."""
    try:
        result = get_models(server)
    except ServerError as err:
        typer.echo(f"models: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None:
        raise typer.Exit(code=1)


@app.command()
def props(
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    model: str | None = typer.Option(None, help="Model id to query; nothing is loaded by default."),
    autoload: bool = typer.Option(False, help="Allow the server to load/pre-warm the model."),
) -> None:
    """Show server properties via GET /props?model=<id> [--model ID]."""
    try:
        result = get_props(server, model=model, autoload=autoload)
    except ServerError as err:
        typer.echo(f"props: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None:
        raise typer.Exit(code=1)


@app.command()
def metrics(
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    model: str | None = typer.Option(None, help="Model id to query (required in router mode)."),
) -> None:
    """Show server metrics via GET /metrics?model=<id> [--model ID].

    Prometheus exposition format; the server must be started with --metrics,
    and router mode requires a model id."""
    try:
        result = get_metrics(server, model=model)
    except ServerError as err:
        typer.echo(f"metrics: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None:
        raise typer.Exit(code=1)


@app.command()
def slots(
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    model: str | None = typer.Option(None, help="Model id to query (required in router mode)."),
) -> None:
    """Show slot state via GET /slots?model=<id> [--model ID]."""
    try:
        result = get_slots(server, model=model)
    except ServerError as err:
        typer.echo(f"slots: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None:
        raise typer.Exit(code=1)


def main() -> None:
    """Entry point for the `llama_server_tool` command and `python -m llama_server_tool`."""
    app()


if __name__ == "__main__":
    main()
