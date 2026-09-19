"""
### POST `/models/load`: Load a model

Load a model

Payload:
- `model`: name of the model to be loaded.

```json
{
  "model": "ggml-org/gemma-3-4b-it-GGUF:Q4_K_M"
}
```

Response:

```json
{
  "success": true
}
```

Router mode only. Fire-and-launch: the response returns when the instance
is spawned (state `loading`), not when the model is ready — wait for ready
with a call that holds, e.g. `GET /slots?model=<id>&autoload=true`.
`is_running` covers `loaded | loading | sleeping`, so a model mid-load or
asleep answers "model is already running". At `--models-max` capacity the
router evicts the LRU running model before spawning the new one.
"""

from typing import Any

from pydantic import BaseModel, ValidationError

from .server import AUTOLOAD_TIMEOUT, ApiError, ServerError, apost_json, post_json, resolve_server_url


class LoadReport(BaseModel):
    """POST /models/load response (or an API error body), plus the requested model id."""

    success: bool = False
    error: ApiError | None = None
    model: str | None = None

    def render(self) -> str:
        """Format the load result for output."""
        if self.error is not None:
            return f"load: {self.error.message}"
        return f"load: {self.model} loading"


def _load_from(status: int, body: dict[str, Any], model: str) -> LoadReport:
    """Validate a /models/load response body as a LoadReport model."""
    if status != 200 and "error" not in body:
        raise ServerError(f"HTTP {status}: {body}")
    try:
        report = LoadReport.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err
    report.model = model
    return report


def _load_timeout(timeout: float | None) -> float:
    """Read timeout for a /models/load request; the server may block on an LRU unload or reload."""
    return timeout if timeout is not None else AUTOLOAD_TIMEOUT


def load_model(model: str, server: str | None = None, timeout: float | None = None) -> LoadReport:
    """Load a model via POST /models/load (router mode).

    Fire-and-launch: the response returns when the instance is spawned
    (state loading); wait for ready with get_slots(model=..., autoload=True)."""
    status, body = post_json(
        resolve_server_url(server), "/models/load", {"model": model}, timeout=_load_timeout(timeout)
    )
    return _load_from(status, body, model)


async def aload_model(model: str, server: str | None = None, timeout: float | None = None) -> LoadReport:
    """Async version of load_model()."""
    status, body = await apost_json(
        resolve_server_url(server), "/models/load", {"model": model}, timeout=_load_timeout(timeout)
    )
    return _load_from(status, body, model)
