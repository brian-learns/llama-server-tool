"""
### POST `/models/unload`: Unload a model

Unload a model

Payload:

```json
{
  "model": "ggml-org/gemma-3-4b-it-GGUF:Q4_K_M",
}
```

Response:

```json
{
  "success": true
}
```

Router mode only. A model in the downloading state is unloadable — this
also serves as the documented "cancel model downloading" mechanism.
Unloading stops the model's instance, interrupting any in-flight
generation on its slots.
"""

from typing import Any

from pydantic import BaseModel, ValidationError

from .server import ApiError, ServerError, apost_json, post_json, resolve_server_url
from .slots import aget_slots, get_slots


class UnloadReport(BaseModel):
    """POST /models/unload response (or an API error body), plus the requested model id."""

    success: bool = False
    error: ApiError | None = None
    model: str | None = None
    busy_slots: int | None = None

    def render(self) -> str:
        """Format the unload result for output."""
        if self.error is not None:
            return f"unload: {self.error.message}"
        if self.busy_slots is not None:
            return f"unload: {self.model} is busy ({self.busy_slots} slot(s) processing); use --force to unload anyway"
        return f"unload: {self.model} unloaded"


def _unload_from(status: int, body: dict[str, Any], model: str) -> UnloadReport:
    """Validate a /models/unload response body as an UnloadReport model."""
    if status != 200 and "error" not in body:
        raise ServerError(f"HTTP {status}: {body}")
    try:
        report = UnloadReport.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err
    report.model = model
    return report


def _busy_slots(model: str, server: str | None) -> int | None:
    """Count processing slots for a model, or None when it cannot be busy.

    autoload=False keeps the check side-effect-free: router proxy routes
    would otherwise load a non-running model (400 'model is not loaded'
    means nothing is processing)."""
    slots_report = get_slots(server, model=model, autoload=False)
    if slots_report.error is not None:
        return None
    return sum(1 for slot in slots_report.slots if slot.is_processing)


def unload_model(model: str, server: str | None = None, force: bool = False) -> UnloadReport:
    """Unload a model via POST /models/unload (router mode).

    Unless force, refuses while any slot is processing (best-effort: a
    request can start between the check and the unload)."""
    if not force:
        busy = _busy_slots(model, server)
        if busy:
            return UnloadReport(model=model, busy_slots=busy)
    status, body = post_json(resolve_server_url(server), "/models/unload", {"model": model})
    return _unload_from(status, body, model)


async def aunload_model(model: str, server: str | None = None, force: bool = False) -> UnloadReport:
    """Async version of unload_model()."""
    if not force:
        slots_report = await aget_slots(server, model=model, autoload=False)
        if slots_report.error is None:
            busy = sum(1 for slot in slots_report.slots if slot.is_processing)
            if busy:
                return UnloadReport(model=model, busy_slots=busy)
    status, body = await apost_json(resolve_server_url(server), "/models/unload", {"model": model})
    return _unload_from(status, body, model)
