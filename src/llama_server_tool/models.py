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

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError

from .server import ApiError, ServerError, afetch_json, fetch_json, resolve_server_url


def format_params(value: int) -> str:
    """Format a parameter count with a decimal unit, e.g. 8030261312 -> '8.03B'."""
    number = float(value)
    for unit in ("", "K", "M", "B"):
        if number < 1000.0 or unit == "B":
            return f"{int(number)}{unit}" if unit == "" else f"{number:.2f}{unit}"
        number /= 1000.0
    raise AssertionError("unreachable")


def format_bytes(value: int) -> str:
    """Format a byte count with a decimal unit, e.g. 4912898304 -> '4.91 GB'."""
    number = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1000.0 or unit == "TB":
            return f"{int(number)} B" if unit == "B" else f"{number:.2f} {unit}"
        number /= 1000.0
    raise AssertionError("unreachable")


def format_created(created: int) -> str:
    """Format a unix timestamp as a UTC string, e.g. 1735142223 -> '2024-12-25 15:57:03 UTC'."""
    return datetime.fromtimestamp(created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class ModelMeta(BaseModel):
    """Model metadata from llama.cpp (the `meta` field of /v1/models)."""

    vocab_type: int
    n_vocab: int
    n_ctx_train: int
    n_embd: int
    n_params: int
    size: int

    def render(self) -> str:
        """Format the metadata lines for output."""
        lines = [
            ("n_params:", format_params(self.n_params)),
            ("n_ctx_train:", self.n_ctx_train),
            ("n_embd:", self.n_embd),
            ("n_vocab:", self.n_vocab),
            ("size:", format_bytes(self.size)),
            ("vocab_type:", self.vocab_type),
        ]
        return "\n".join(f"    {label:<13}{value}" for label, value in lines)


class ModelInfo(BaseModel):
    """A single model entry from /v1/models."""

    id: str
    object: str = "model"
    created: int
    owned_by: str
    meta: ModelMeta | None = None

    def render(self) -> str:
        """Format the model info lines for output."""
        lines = [
            f"  id:         {self.id}",
            f"  created:    {format_created(self.created)}",
            f"  owned_by:   {self.owned_by}",
        ]
        if self.meta is None:
            lines.append("  meta: (null — model may still be loading)")
        else:
            lines.extend(("  meta:", self.meta.render()))
        return "\n".join(lines)


class ModelList(BaseModel):
    """`GET /v1/models` response body, validated and rendered by pydantic."""

    object: str = "list"
    data: list[ModelInfo] = []
    error: ApiError | None = None

    def render(self) -> str:
        """Format the model list for output."""
        if self.error is not None:
            return f"models: {self.error.message}"
        body = "\n".join(info.render() for info in self.data)
        return f"models:\n{body}"

    def match(self, query: str) -> "ModelList":
        """Return only the entries whose id equals the query (exact match)."""
        return ModelList(data=[info for info in self.data if info.id == query])


def _models_from(body: dict[str, Any]) -> ModelList:
    """Validate a /v1/models response body as a ModelList model."""
    try:
        return ModelList.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err


def get_models(server: str | None = None) -> ModelList:
    """Query GET /v1/models and return the validated ModelList model."""
    _, body = fetch_json(resolve_server_url(server), "/v1/models")
    return _models_from(body)


async def aget_models(server: str | None = None) -> ModelList:
    """Async version of get_models()."""
    _, body = await afetch_json(resolve_server_url(server), "/v1/models")
    return _models_from(body)
