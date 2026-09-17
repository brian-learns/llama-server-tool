"""
### GET `/v1/models`: OpenAI-compatible Model Info API

Returns information about the loaded model. See [OpenAI Models API documentation](https://platform.openai.com/docs/api-reference/models).

The returned list always has one single element. The `meta` field can be `null` (for example, while the model is still loading).

By default, model `id` field is the path to model file, specified via `-m`. You can set a custom value for model `id` field via `--alias` argument. For example, `--alias gpt-4o-mini`.

Example:

```json
{
    "object": "list",
    "data": [
        {
            "id": "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
            "object": "model",
            "created": 1735142223,
            "owned_by": "llamacpp",
            "meta": {
                "vocab_type": 2,
                "n_vocab": 128256,
                "n_ctx_train": 131072,
                "n_embd": 4096,
                "n_params": 8030261312,
                "size": 4912898304
            }
        }
    ]
}
```
"""

from collections.abc import Sequence
from typing import Any, Literal, overload

from pydantic import BaseModel, ValidationError

from .server import (
    ApiError,
    ServerError,
    afetch,
    afetch_json,
    fetch,
    fetch_json,
    format_value,
    resolve_server_url,
)


def format_params(value: int) -> str:
    """Format a parameter count with a decimal unit, e.g. 8030261312 -> '8.03B'."""
    number = float(value)
    for unit in ("", "K", "M", "B"):
        if number < 1000.0 or unit == "B":
            return f"{int(number)}{unit}" if unit == "" else f"{number:.2f}{unit}"
        number /= 1000.0
    raise AssertionError("unreachable")


def format_bytes(value: int) -> str:
    """Format a byte count with a decimal unit, e.g. 4912898304 -> '4.91GB'."""
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1000.0 or unit == "TB":
            return f"{int(number)}{unit}" if unit == "B" else f"{number:.2f}{unit}"
        number /= 1000.0
    raise AssertionError("unreachable")


class ModelArchitecture(BaseModel):
    """The `architecture` field of /v1/models: which modalities a model accepts and produces."""

    input_modalities: list[str] = []
    output_modalities: list[str] = []


def _arg_value(args: list[str], flag: str) -> str | None:
    """Return the value following flag in a CLI-style args list, or None."""
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
    return None


class ModelStatus(BaseModel):
    """Router-mode registry status: load state plus the subprocess launch args."""

    value: str | None = None
    args: list[str] = []

    @property
    def port(self) -> int | None:
        """The subprocess --port argument, if present."""
        raw = _arg_value(self.args, "--port")
        return int(raw) if raw is not None and raw.isdigit() else None

    @property
    def host(self) -> str | None:
        """The subprocess --host argument, if present."""
        return _arg_value(self.args, "--host")


class ModelInfo(BaseModel):
    """A single model entry from /v1/models."""

    id: str
    object: str = "model"
    created: int
    owned_by: str
    meta: dict[str, Any] | None = None
    architecture: ModelArchitecture | None = None
    status: ModelStatus | None = None


DEFAULT_META_FIELDS = ["n_params", "n_ctx_train", "n_embd", "n_vocab", "size", "vocab_type"]


class ModelList(BaseModel):
    """`GET /v1/models` response body, validated and rendered by pydantic."""

    object: str = "list"
    data: list[ModelInfo] = []
    error: ApiError | None = None

    def match(self, query: str) -> "ModelList":
        """Return only the entries whose id equals the query (exact match)."""
        return ModelList(data=[info for info in self.data if info.id == query])

    def select(
        self,
        loaded: bool = False,
        input_modalities: Sequence[str] = (),
        output_modalities: Sequence[str] = (),
    ) -> "ModelList":
        """Filter entries by load state and modalities (each entry must support every requested modality)."""
        data = self.data
        if loaded:
            data = [info for info in data if info.status is not None and info.status.value == "loaded"]
        if input_modalities:
            data = [
                info
                for info in data
                if info.architecture is not None and set(input_modalities) <= set(info.architecture.input_modalities)
            ]
        if output_modalities:
            data = [
                info
                for info in data
                if info.architecture is not None and set(output_modalities) <= set(info.architecture.output_modalities)
            ]
        return ModelList(data=data)

    def render(
        self,
        show_modalities: bool = False,
        show_meta: bool = False,
        meta_fields: Sequence[str] | None = None,
    ) -> str:
        """Format the model list: quoted ids, or a table with optional modality/meta columns."""
        if self.error is not None:
            return f"models: {self.error.message}"
        if not self.data:
            return ""
        if not (show_modalities or show_meta):
            return "\n".join(f'"{info.id}"' for info in self.data)
        fields = list(meta_fields) if meta_fields is not None else DEFAULT_META_FIELDS
        if show_meta and meta_fields is not None:
            available = set().union(*(info.meta.keys() for info in self.data if info.meta is not None))
            unknown = [field for field in fields if field not in available]
            if unknown:
                raise ValueError(
                    f"unknown meta field(s) {', '.join(unknown)} (available: {', '.join(sorted(available))})"
                )
        rows: list[list[str]] = [["id"]]
        if show_modalities:
            rows[0] += ["input", "output"]
        if show_meta:
            rows[0] += fields
        for info in self.data:
            row = [f'"{info.id}"']
            if show_modalities:
                arch = info.architecture
                row += [
                    ",".join(arch.input_modalities) if arch is not None else "",
                    ",".join(arch.output_modalities) if arch is not None else "",
                ]
            if show_meta:
                row += [self._meta_cell(info, field) for field in fields]
            rows.append(row)
        widths = [max(len(cell) for cell in column) for column in zip(*rows, strict=True)]
        return "\n".join(
            " ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip() for row in rows
        )

    @staticmethod
    def _meta_cell(info: ModelInfo, field: str) -> str:
        """Format one meta value: n_params/size humanized, everything else via format_value."""
        meta = info.meta
        if meta is None or field not in meta:
            return ""
        value = meta[field]
        if field == "n_params":
            return format_params(value)
        if field == "size":
            return format_bytes(value)
        return format_value(value)


def _models_from(body: dict[str, Any]) -> ModelList:
    """Validate a /v1/models response body as a ModelList model."""
    try:
        return ModelList.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err


@overload
def get_models(server: str | None = None, *, raw: Literal[True]) -> tuple[int, str]:
    """Raw variant: return (status, body) without validation."""


@overload
def get_models(server: str | None = None, raw: bool = False) -> ModelList:
    """Return the validated model (default)."""


def get_models(server: str | None = None, raw: bool = False) -> "ModelList | tuple[int, str]":
    """Query GET /v1/models; returns the validated ModelList, or (status, body) with raw=True."""
    if raw:
        return fetch(resolve_server_url(server), "/v1/models")
    _, body = fetch_json(resolve_server_url(server), "/v1/models")
    return _models_from(body)


@overload
async def aget_models(server: str | None = None, *, raw: Literal[True]) -> tuple[int, str]:
    """Raw variant: return (status, body) without validation."""


@overload
async def aget_models(server: str | None = None, raw: bool = False) -> ModelList:
    """Return the validated model (default)."""


async def aget_models(server: str | None = None, raw: bool = False) -> "ModelList | tuple[int, str]":
    """Async version of get_models()."""
    if raw:
        return await afetch(resolve_server_url(server), "/v1/models")
    _, body = await afetch_json(resolve_server_url(server), "/v1/models")
    return _models_from(body)
