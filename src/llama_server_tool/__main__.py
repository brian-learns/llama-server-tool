# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Command line tool to administer a local llama-server."""

import json

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
def health(
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    json: bool = typer.Option(False, help="Print the raw JSON response body instead of the formatted report."),
) -> None:
    """Check server health via GET /health."""
    if json:
        try:
            status, body = check_health(server, raw=True)
        except ServerError as err:
            typer.echo(f"health: {err}", err=True)
            raise typer.Exit(code=1) from err
        typer.echo(body)
        raise typer.Exit(code=0 if 200 <= status < 300 else 1)
    try:
        result = check_health(server)
    except ServerError as err:
        typer.echo(f"health: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None or result.status != "ok":
        raise typer.Exit(code=1)


def _filter_models_json(body: str, model: str) -> tuple[str, bool]:
    """Filter a raw /v1/models JSON body to entries whose id equals model (exact match).

    Returns (filtered JSON, whether anything matched). Operates on the parsed
    body, not the pydantic model, so fields the model ignores are preserved.
    """
    parsed = json.loads(body)
    data = parsed.get("data")
    if not isinstance(data, list):
        raise ValueError("missing data list")
    parsed["data"] = [entry for entry in data if isinstance(entry, dict) and entry.get("id") == model]
    return json.dumps(parsed, indent=2), bool(parsed["data"])


@app.command()
def models(
    model: str | None = typer.Argument(None, help="Model id to show (exact match)."),
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    json: bool = typer.Option(False, help="Print the raw JSON response body instead of the formatted report."),
) -> None:
    """Show the loaded model via GET /v1/models [MODEL]."""
    if json:
        try:
            status, body = get_models(server, raw=True)
        except ServerError as err:
            typer.echo(f"models: {err}", err=True)
            raise typer.Exit(code=1) from err
        if 200 <= status < 300 and model is not None:
            try:
                body, matched = _filter_models_json(body, model)
            except ValueError as err:
                typer.echo(f"models: invalid JSON from /v1/models: {err}", err=True)
                raise typer.Exit(code=1) from err
            if not matched:
                typer.echo(f"models: no model with id '{model}'", err=True)
                raise typer.Exit(code=1)
        typer.echo(body)
        raise typer.Exit(code=0 if 200 <= status < 300 else 1)
    try:
        result = get_models(server)
    except ServerError as err:
        typer.echo(f"models: {err}", err=True)
        raise typer.Exit(code=1) from err
    if model is not None and result.error is None:
        result = result.match(model)
        if not result.data:
            typer.echo(f"models: no model with id '{model}'", err=True)
            raise typer.Exit(code=1)
    typer.echo(result.render())
    if result.error is not None:
        raise typer.Exit(code=1)


@app.command()
def props(
    model: str | None = typer.Argument(None, help="Model id to query; nothing is loaded by default."),
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    autoload: bool = typer.Option(False, help="Allow the server to load/pre-warm the model."),
    timeout: float | None = typer.Option(None, help="Read timeout in seconds (default 5; 300 with --autoload)."),
    json: bool = typer.Option(
        False, help="Print the raw JSON response body instead of the report (includes chat_template)."
    ),
) -> None:
    """Show server properties via GET /props?model=<id> [MODEL]."""
    if json:
        try:
            status, body = get_props(server, model=model, autoload=autoload, timeout=timeout, raw=True)
        except ServerError as err:
            typer.echo(f"props: {err}", err=True)
            raise typer.Exit(code=1) from err
        typer.echo(body)
        raise typer.Exit(code=0 if 200 <= status < 300 else 1)
    try:
        result = get_props(server, model=model, autoload=autoload, timeout=timeout)
    except ServerError as err:
        typer.echo(f"props: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None:
        raise typer.Exit(code=1)


@app.command()
def metrics(
    model: str | None = typer.Argument(None, help="Model id to query (required in router mode)."),
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
) -> None:
    """Show server metrics via GET /metrics?model=<id> [MODEL].

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
    model: str | None = typer.Argument(None, help="Model id to query (required in router mode)."),
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    json: bool = typer.Option(False, help="Print the raw JSON response body instead of the formatted report."),
) -> None:
    """Show slot state via GET /slots?model=<id> [MODEL]."""
    if json:
        try:
            status, body = get_slots(server, model=model, raw=True)
        except ServerError as err:
            typer.echo(f"slots: {err}", err=True)
            raise typer.Exit(code=1) from err
        typer.echo(body)
        raise typer.Exit(code=0 if 200 <= status < 300 else 1)
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
