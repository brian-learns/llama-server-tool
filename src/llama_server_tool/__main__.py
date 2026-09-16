# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Command line tool to administer a local llama-server."""

import json

import typer
from pydantic import ValidationError

from .health import Health
from .metrics import MetricsReport, parse_exposition
from .models import ModelList
from .props import Props
from .server import ServerError, fetch, fetch_json, resolve_server_url

app = typer.Typer()


# Without an explicit callback, typer collapses a single registered command into the
# root command, which would break the `llama-server-tool health` subcommand form.
@app.callback()
def main_callback() -> None:
    """Administer a local llama-server."""


@app.command()
def health(server: str | None = typer.Option(None, help="Base URL of the llama-server.")) -> None:
    """Check server health via GET /health."""
    base = resolve_server_url(server)
    try:
        _, body = fetch_json(base, "/health")
    except ServerError as err:
        typer.echo(f"health: {err}", err=True)
        raise typer.Exit(code=1) from err
    try:
        result = Health.model_validate(body)
    except ValidationError as err:
        typer.echo(f"health: invalid response body: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None or result.status != "ok":
        raise typer.Exit(code=1)


@app.command()
def models(server: str | None = typer.Option(None, help="Base URL of the llama-server.")) -> None:
    """Show the loaded model via GET /v1/models."""
    base = resolve_server_url(server)
    try:
        status, body = fetch_json(base, "/v1/models")
    except ServerError as err:
        typer.echo(f"models: {err}", err=True)
        raise typer.Exit(code=1) from err
    try:
        result = ModelList.model_validate(body)
    except ValidationError as err:
        typer.echo(f"models: invalid response body: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None or status != 200:
        raise typer.Exit(code=1)


@app.command()
def props(
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    model: str | None = typer.Option(None, help="Model id to query; nothing is loaded by default."),
    autoload: bool = typer.Option(False, help="Allow the server to load/pre-warm the model."),
) -> None:
    """Show server properties via GET /props."""
    base = resolve_server_url(server)
    params = None
    if model is not None:
        params = {"model": model, "autoload": "true" if autoload else "false"}
    try:
        status, body = fetch_json(base, "/props", params=params)
    except ServerError as err:
        typer.echo(f"props: {err}", err=True)
        raise typer.Exit(code=1) from err
    try:
        result = Props.model_validate(body)
    except ValidationError as err:
        typer.echo(f"props: invalid response body: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.error is not None or status != 200:
        raise typer.Exit(code=1)


@app.command()
def metrics(
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    model: str | None = typer.Option(None, help="Model id to query (required in router mode)."),
) -> None:
    """Show server metrics via GET /metrics (Prometheus format)."""
    base = resolve_server_url(server)
    params = {"model": model} if model is not None else None
    try:
        status, text = fetch(base, "/metrics", params=params)
    except ServerError as err:
        typer.echo(f"metrics: {err}", err=True)
        raise typer.Exit(code=1) from err
    if status != 200:
        try:
            result = MetricsReport.model_validate(json.loads(text))
        except ValueError:
            typer.echo(f"metrics: HTTP {status}: {text.strip()}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(result.render())
        raise typer.Exit(code=1)
    try:
        families = parse_exposition(text)
    except ValueError as err:
        typer.echo(f"metrics: failed to parse exposition text: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(MetricsReport(families=families).render())


def main() -> None:
    """Entry point for the `llama_server_tool` command and `python -m llama_server_tool`."""
    app()


if __name__ == "__main__":
    main()
