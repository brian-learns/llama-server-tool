"""
### **GET** `/props`: Get server global properties.

By default, it is read-only. To make POST request to change global properties, you need to start server with `--props`

**Response format**

```json
{
  "default_generation_settings": {
    "id": 0,
    "id_task": -1,
    "n_ctx": 1024,
    "speculative": false,
    "is_processing": false,
    "params": {
      "n_predict": -1,
      "seed": 4294967295,
      "temperature": 0.800000011920929,
      "dynatemp_range": 0.0,
      "dynatemp_exponent": 1.0,
      "top_k": 40,
      "top_p": 0.949999988079071,
      "min_p": 0.05000000074505806,
      "xtc_probability": 0.0,
      "xtc_threshold": 0.10000000149011612,
      "typical_p": 1.0,
      "repeat_last_n": 64,
      "repeat_penalty": 1.0,
      "presence_penalty": 0.0,
      "frequency_penalty": 0.0,
      "dry_multiplier": 0.0,
      "dry_base": 1.75,
      "dry_allowed_length": 2,
      "dry_penalty_last_n": 64,
      "dry_sequence_breakers": [
        "\n",
        ":",
        "\"",
        "*"
      ],
      "mirostat": 0,
      "mirostat_tau": 5.0,
      "mirostat_eta": 0.10000000149011612,
      "stop": [],
      "max_tokens": -1,
      "n_keep": 0,
      "n_discard": 0,
      "ignore_eos": false,
      "stream": true,
      "n_probs": 0,
      "min_keep": 0,
      "grammar": "",
      "samplers": [
        "dry",
        "top_k",
        "typ_p",
        "top_p",
        "min_p",
        "xtc",
        "temperature"
      ],
      "speculative.n_max": 16,
      "speculative.n_min": 5,
      "speculative.p_min": 0.8999999761581421,
      "timings_per_token": false
    },
    "prompt": "",
    "next_token": {
      "has_next_token": true,
      "has_new_line": false,
      "n_remain": -1,
      "n_decoded": 0,
      "stopping_word": ""
    }
  },
  "total_slots": 1,
  "model_path": "../models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
  "chat_template": "...",
  "chat_template_caps": {},
  "modalities": {
    "vision": false
  },
  "media_marker": "<__media_YoNhud46VdDqbuFmKYEO9PY7A4ARzRfg__>",
  "build_info": "b(build number)-(build commit hash)",
  "is_sleeping": false
}
```

- `default_generation_settings` - the default generation settings for the `/completion` endpoint, which has the same fields as the `generation_settings` response object from the `/completion` endpoint.
- `total_slots` - the total number of slots for process requests (defined by `--parallel` option)
- `model_path` - the path to model file (same with `-m` argument)
- `chat_template` - the model's original Jinja2 prompt template
- `chat_template_caps` - capabilities of the chat template (see `common/jinja/caps.h` for more info)
- `modalities` - the list of supported modalities
- `is_sleeping` - sleeping status, see [Sleeping on idle](#sleeping-on-idle)

"""

from typing import Any, Literal, overload

from pydantic import BaseModel, Field, ValidationError

from .server import (
    AUTOLOAD_TIMEOUT,
    ApiError,
    ServerError,
    afetch,
    afetch_json,
    fetch,
    fetch_json,
    format_value,
    resolve_server_url,
)


class GenerationParams(BaseModel):
    """Curated generation params from /props; all optional, extras ignored."""

    n_predict: int | None = None
    seed: int | None = None
    temperature: float | None = None
    dynatemp_range: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    min_p: float | None = None
    typical_p: float | None = None
    repeat_last_n: int | None = None
    repeat_penalty: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    mirostat: int | None = None
    mirostat_tau: float | None = None
    mirostat_eta: float | None = None
    stop: list[str] | None = None
    max_tokens: int | None = None
    n_keep: int | None = None
    ignore_eos: bool | None = None
    stream: bool | None = None
    samplers: list[str] | None = None

    def render_lines(self) -> list[tuple[str, str]]:
        """Return (label, value) lines for the params that are present and non-empty."""
        return [
            (f"{key}:", format_value(value)) for key, value in self.model_dump(exclude_none=True).items() if value != []
        ]


class DefaultGenerationSettings(BaseModel):
    """The default generation settings section of /props."""

    id: int | None = None
    n_ctx: int | None = None
    speculative: bool | None = None
    is_processing: bool | None = None
    params: GenerationParams | None = None


class Props(BaseModel):
    """`GET /props` response body, validated and rendered by pydantic."""

    default_generation_settings: DefaultGenerationSettings | None = None
    total_slots: int | None = None
    model_path: str | None = None
    # Captured for validation only; render() never emits its content (raw Jinja).
    chat_template: str | None = Field(default=None, repr=False)
    chat_template_caps: dict[str, Any] | None = None
    modalities: dict[str, bool] | None = None
    is_sleeping: bool | None = None
    build_info: str | None = None
    error: ApiError | None = None

    def render(self) -> str:
        """Format the props report; the chat template content is never included."""
        if self.error is not None:
            return f"props: {self.error.message}"
        lines = ["props:"]
        top: list[tuple[str, str]] = []
        if self.model_path is not None:
            top.append(("model_path:", self.model_path))
        if self.total_slots is not None:
            top.append(("total_slots:", str(self.total_slots)))
        if self.is_sleeping is not None:
            top.append(("is_sleeping:", format_value(self.is_sleeping)))
        if self.modalities:
            top.append(("modalities:", ", ".join(f"{k}={format_value(v)}" for k, v in self.modalities.items())))
        if self.build_info is not None:
            top.append(("build_info:", self.build_info))
        if self.chat_template is not None:
            top.append(("chat_template:", f"<hidden: {len(self.chat_template)} chars>"))
        lines.extend(f"  {label:<21}{value}" for label, value in top)
        if self.default_generation_settings is not None:
            lines.append("  generation settings:")
            settings = self.default_generation_settings
            subs = [
                (f"{key}:", format_value(value))
                for key, value in settings.model_dump(exclude_none=True, exclude={"params"}).items()
            ]
            lines.extend(f"    {label:<15}{value}" for label, value in subs)
            if settings.params is not None:
                params = settings.params.render_lines()
                if params:
                    lines.append("        params:")
                    lines.extend(f"          {label:<19}{value}" for label, value in params)
        return "\n".join(lines)


def _props_params(model: str | None, autoload: bool) -> dict[str, str] | None:
    """Build the /props query params; None when no model is queried."""
    if model is None:
        return None
    return {"model": model, "autoload": "true" if autoload else "false"}


def _props_from(body: dict[str, Any]) -> Props:
    """Validate a /props response body as a Props model."""
    try:
        return Props.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err


def _props_timeout(autoload: bool, timeout: float | None) -> float | None:
    """Read timeout for a /props request; autoload holds the response until the model loads."""
    if timeout is not None:
        return timeout
    return AUTOLOAD_TIMEOUT if autoload else None


@overload
def get_props(
    server: str | None = None,
    *,
    raw: Literal[True],
    model: str | None = None,
    autoload: bool = False,
    timeout: float | None = None,
) -> tuple[int, str]:
    """Raw variant: return (status, body) without validation."""


@overload
def get_props(
    server: str | None = None,
    model: str | None = None,
    autoload: bool = False,
    timeout: float | None = None,
    raw: bool = False,
) -> Props:
    """Return the validated model (default)."""


def get_props(
    server: str | None = None,
    model: str | None = None,
    autoload: bool = False,
    timeout: float | None = None,
    raw: bool = False,
) -> "Props | tuple[int, str]":
    """Query GET /props; returns the validated Props model, or (status, body) with raw=True."""
    params = _props_params(model, autoload)
    read_timeout = _props_timeout(autoload, timeout)
    if raw:
        return fetch(resolve_server_url(server), "/props", params=params, timeout=read_timeout)
    _, body = fetch_json(resolve_server_url(server), "/props", params=params, timeout=read_timeout)
    return _props_from(body)


@overload
async def aget_props(
    server: str | None = None,
    *,
    raw: Literal[True],
    model: str | None = None,
    autoload: bool = False,
    timeout: float | None = None,
) -> tuple[int, str]:
    """Raw variant: return (status, body) without validation."""


@overload
async def aget_props(
    server: str | None = None,
    model: str | None = None,
    autoload: bool = False,
    timeout: float | None = None,
    raw: bool = False,
) -> Props:
    """Return the validated model (default)."""


async def aget_props(
    server: str | None = None,
    model: str | None = None,
    autoload: bool = False,
    timeout: float | None = None,
    raw: bool = False,
) -> "Props | tuple[int, str]":
    """Async version of get_props()."""
    params = _props_params(model, autoload)
    read_timeout = _props_timeout(autoload, timeout)
    if raw:
        return await afetch(resolve_server_url(server), "/props", params=params, timeout=read_timeout)
    _, body = await afetch_json(resolve_server_url(server), "/props", params=params, timeout=read_timeout)
    return _props_from(body)
