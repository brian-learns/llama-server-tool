"""
### GET `/health`: Returns health check result

This endpoint is public (no API key check). `/v1/health` also works.

**Response format**

- HTTP status code 503
  - Body: `{"error": {"code": 503, "message": "Loading model", "type": "unavailable_error"}}`
  - Explanation: the model is still being loaded.
- HTTP status code 200
  - Body: `{"status": "ok" }`
  - Explanation: the model is successfully loaded and the server is ready.
"""

from typing import Any

from pydantic import BaseModel, ValidationError

from .server import ApiError, ServerError, afetch_json, fetch_json, resolve_server_url


class Health(BaseModel):
    """`GET /health` response body, validated and rendered by pydantic."""

    status: str | None = None
    error: ApiError | None = None

    def render(self) -> str:
        """Format the health result for output."""
        if self.status is not None:
            return f"health: {self.status}"
        if self.error is not None:
            return f"health: {self.error.message}"
        return "health: unknown response"


def _health_from(body: dict[str, Any]) -> Health:
    """Validate a /health response body as a Health model."""
    try:
        return Health.model_validate(body)
    except ValidationError as err:
        raise ServerError(f"invalid response body: {err}") from err


def check_health(server: str | None = None) -> Health:
    """Query GET /health and return the validated Health model."""
    _, body = fetch_json(resolve_server_url(server), "/health")
    return _health_from(body)


async def aget_health(server: str | None = None) -> Health:
    """Async version of check_health()."""
    _, body = await afetch_json(resolve_server_url(server), "/health")
    return _health_from(body)
