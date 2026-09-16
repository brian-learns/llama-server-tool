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

from pydantic import BaseModel

from .server import ApiError


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
