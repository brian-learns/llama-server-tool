# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""Command line tool to administer a local llama-server."""

import os

import httpx
import typer
from pydantic import ValidationError

from .health import Health

app = typer.Typer()


# Without an explicit callback, typer collapses a single registered command into the
# root command, which would break the `llama-server-tool health` subcommand form.
@app.callback()
def main_callback() -> None:
    """Administer a local llama-server."""


DEFAULT_SERVER = "http://127.0.0.0:8080"
REQUEST_TIMEOUT = 5.0


def resolve_server_url(server: str | None = None) -> str:
    """Resolve the server base URL: option, then LLAMA_SERVER_URL, then default."""
    url = server or os.environ.get("LLAMA_SERVER_URL") or DEFAULT_SERVER
    return url.rstrip("/")


@app.command()
def health(server: str | None = typer.Option(None, help="Base URL of the llama-server.")) -> None:
    """Check server health via GET /health."""
    base = resolve_server_url(server)
    try:
        response = httpx.get(f"{base}/health", timeout=REQUEST_TIMEOUT)
    except httpx.HTTPError as err:
        typer.echo(f"health: {err}", err=True)
        raise typer.Exit(code=1) from err
    try:
        result = Health.model_validate_json(response.text)
    except ValidationError as err:
        typer.echo(f"health: invalid response body: {err}", err=True)
        raise typer.Exit(code=1) from err
    typer.echo(result.render())
    if result.status != "ok":
        raise typer.Exit(code=1)


def main() -> None:
    """Entry point for the `llama_server_tool` command and `python -m llama_server_tool`."""
    app()


if __name__ == "__main__":
    main()
