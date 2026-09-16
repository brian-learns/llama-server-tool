# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Command line tool to administer a local llama-server."""

import typer
from pydantic import ValidationError

from .health import Health
from .models import ModelList
from .server import ServerError, fetch_json, resolve_server_url

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


def main() -> None:
    """Entry point for the `llama_server_tool` command and `python -m llama_server_tool`."""
    app()


if __name__ == "__main__":
    main()
