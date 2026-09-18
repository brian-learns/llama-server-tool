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
from .status import get_status

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
    reload: bool = typer.Option(
        False,
        help=(
            "Refresh the model list from the models dir first (?reload=1). Loaded models whose source was updated "
            "or removed are UNLOADED; nothing is loaded. The refreshed list is printed."
        ),
    ),
    loaded: bool = typer.Option(False, help="Only show loaded models."),
    # B008: typer materializes the list default itself; None is the safe default
    # explicit --input_modalities names: typer would otherwise dash-ify the parameter name
    input_modalities: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--input_modalities",
        help="Only show models accepting all of these input modalities (repeatable, comma-separated).",
    ),
    output_modalities: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--output_modalities",
        help="Only show models producing all of these output modalities (repeatable, comma-separated).",
    ),
    show_modalities: bool = typer.Option(False, help="Add input/output modality columns."),
    show_meta: bool = typer.Option(False, help="Add meta columns (implies --loaded)."),
    meta_fields: list[str] | None = typer.Option(None, help="Meta fields to show (implies --show-meta)."),  # noqa: B008
    json: bool = typer.Option(False, help="Print the raw JSON response body instead of the formatted report."),
) -> None:
    """Show the model registry as quoted ids via GET /v1/models [MODEL].

    --reload refreshes the list from the models dir first (mutating: see
    --help). Filters: --loaded, --input_modalities, --output_modalities.
    Table columns: --show-modalities, --show-meta (with --meta-fields)."""
    # typer list options do not split commas; accept both `--opt a,b` and repeated flags
    meta_fields_given = meta_fields is not None
    input_modalities = [modality for part in (input_modalities or []) for modality in part.split(",")]
    output_modalities = [modality for part in (output_modalities or []) for modality in part.split(",")]
    meta_fields = [field for part in (meta_fields or []) for field in part.split(",")]
    if json:
        conflicting = [
            flag
            for flag, given in (
                ("--loaded", loaded),
                ("--input_modalities", input_modalities),
                ("--output_modalities", output_modalities),
                ("--show-modalities", show_modalities),
                ("--show-meta", show_meta),
                ("--meta-fields", meta_fields),
            )
            if given
        ]
        if conflicting:
            typer.echo(f"models: --json cannot be combined with {', '.join(conflicting)}", err=True)
            raise typer.Exit(code=1)
        try:
            status, body = get_models(server, raw=True, reload=reload)
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
    show_meta = show_meta or meta_fields_given
    loaded = loaded or show_meta
    try:
        result = get_models(server, reload=reload)
    except ServerError as err:
        typer.echo(f"models: {err}", err=True)
        raise typer.Exit(code=1) from err
    if result.error is None:
        result = result.select(
            loaded=loaded,
            input_modalities=input_modalities or [],
            output_modalities=output_modalities or [],
        )
        if model is not None:
            result = result.match(model)
            if not result.data:
                typer.echo(f"models: no model with id '{model}'", err=True)
                raise typer.Exit(code=1)
        try:
            body = result.render(
                show_modalities=show_modalities,
                show_meta=show_meta,
                meta_fields=meta_fields if meta_fields_given else None,
            )
        except ValueError as err:
            typer.echo(f"models: {err}", err=True)
            raise typer.Exit(code=1) from err
    else:
        body = result.render()
    if body:
        typer.echo(body)
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


@app.command()
def status(
    model: str | None = typer.Argument(None, help="Model id to show (exact match, must be loaded)."),
    server: str | None = typer.Option(None, help="Base URL of the llama-server."),
    no_system: bool = typer.Option(False, "--no-system", help="Omit the free/nvidia-smi footer."),
) -> None:
    """Show a watch-friendly board: per-model memory and slot state."""
    try:
        report = get_status(server, model=model, include_system=not no_system)
    except ServerError as err:
        typer.echo(f"status: {err}", err=True)
        raise typer.Exit(code=1) from err
    if model is not None and report.error is None and not report.blocks:
        typer.echo(f"status: no loaded model with id '{model}'", err=True)
        raise typer.Exit(code=1)
    typer.echo(report.render())
    if report.error is not None:
        raise typer.Exit(code=1)


def main() -> None:
    """Entry point for the `llama_server_tool` command and `python -m llama_server_tool`."""
    app()


if __name__ == "__main__":
    main()
