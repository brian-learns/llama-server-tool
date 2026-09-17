"""
### GET `/slots`: Returns the current slots processing state

This endpoint is enabled by default and can be disabled with `--no-slots`. It can be used to query various per-slot metrics, such as speed, processed tokens, sampling parameters, etc.

If query param `?fail_on_no_slot=1` is set, this endpoint will respond with status code 503 if there is no available slots.

**Response format**

<details>
<summary>Example with 2 slots</summary>

```json
[
  {
    "id": 0,
    "id_task": 135,
    "n_ctx": 65536,
    "speculative": false,
    "is_processing": true,
    "params": {
      "n_predict": -1,
      "seed": 4294967295,
      "temperature": 0.800000011920929,
      "dynatemp_range": 0.0,
      "dynatemp_exponent": 1.0,
      "top_k": 40,
      "top_p": 0.949999988079071,
      "min_p": 0.05000000074505806,
      "top_n_sigma": -1.0,
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
      "dry_penalty_last_n": 131072,
      "mirostat": 0,
      "mirostat_tau": 5.0,
      "mirostat_eta": 0.10000000149011612,
      "max_tokens": -1,
      "n_keep": 0,
      "n_discard": 0,
      "ignore_eos": false,
      "stream": true,
      "n_probs": 0,
      "min_keep": 0,
      "chat_format": "GPT-OSS",
      "reasoning_format": "none",
      "reasoning_in_content": false,
      "generation_prompt": "",
      "samplers": [
        "penalties",
        "dry",
        "top_k",
        "typ_p",
        "top_p",
        "min_p",
        "xtc",
        "temperature"
      ],
      "speculative.n_max": 16,
      "speculative.n_min": 0,
      "speculative.p_min": 0.75,
      "timings_per_token": false,
      "post_sampling_probs": false,
      "lora": []
    },
    "next_token": {
      "has_next_token": true,
      "has_new_line": false,
      "n_remain": -1,
      "n_decoded": 0
    }
  },
  {
    "id": 1,
    "id_task": 0,
    "n_ctx": 65536,
    "speculative": false,
    "is_processing": true,
    "params": {
      "n_predict": -1,
      "seed": 4294967295,
      "temperature": 0.800000011920929,
      "dynatemp_range": 0.0,
      "dynatemp_exponent": 1.0,
      "top_k": 40,
      "top_p": 0.949999988079071,
      "min_p": 0.05000000074505806,
      "top_n_sigma": -1.0,
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
      "dry_penalty_last_n": 131072,
      "mirostat": 0,
      "mirostat_tau": 5.0,
      "mirostat_eta": 0.10000000149011612,
      "max_tokens": -1,
      "n_keep": 0,
      "n_discard": 0,
      "ignore_eos": false,
      "stream": true,
      "n_probs": 0,
      "min_keep": 0,
      "chat_format": "GPT-OSS",
      "reasoning_format": "none",
      "reasoning_in_content": false,
      "generation_prompt": "",
      "samplers": [
        "penalties",
        "dry",
        "top_k",
        "typ_p",
        "top_p",
        "min_p",
        "xtc",
        "temperature"
      ],
      "speculative.n_max": 16,
      "speculative.n_min": 0,
      "speculative.p_min": 0.75,
      "timings_per_token": false,
      "post_sampling_probs": false,
      "lora": []
    },
    "next_token": {
      "has_next_token": true,
      "has_new_line": true,
      "n_remain": -1,
      "n_decoded": 136
    }
  }
]
```
"""

import json

from pydantic import BaseModel, ValidationError

from .props import GenerationParams
from .server import ApiError, ServerError, afetch, fetch, format_value, resolve_server_url


class SlotNextToken(BaseModel):
    """The `next_token` section of a slot."""

    has_next_token: bool | None = None
    has_new_line: bool | None = None
    n_remain: int | None = None
    n_decoded: int | None = None


class Slot(BaseModel):
    """A single slot from GET /slots; all optional, extras ignored."""

    id: int | None = None
    id_task: int | None = None
    n_ctx: int | None = None
    speculative: bool | None = None
    is_processing: bool | None = None
    params: GenerationParams | None = None
    # A list (one entry per in-flight sequence) on some builds; a dict otherwise.
    next_token: SlotNextToken | list[SlotNextToken] | None = None

    def render(self) -> str:
        """Format the slot block for output; only present fields are shown."""
        lines = [f"  slot {self.id}:"]
        entries = [
            ("is_processing:", self.is_processing),
            ("n_ctx:", self.n_ctx),
            ("speculative:", self.speculative),
            ("id_task:", self.id_task),
        ]
        if self.next_token is not None:
            token = self.next_token[0] if isinstance(self.next_token, list) else self.next_token
            entries.extend([("n_decoded:", token.n_decoded), ("n_remain:", token.n_remain)])
        for label, value in entries:
            if value is not None:
                lines.append(f"    {label:<15}{format_value(value)}")
        return "\n".join(lines)


class SlotsReport(BaseModel):
    """GET /slots response (array of slots) or an API error body, rendered by pydantic."""

    slots: list[Slot] = []
    error: ApiError | None = None
    model_name: str | None = None

    def render(self) -> str:
        """Format the slots report; the queried model id leads the header."""
        if self.error is not None:
            return f"slots: {self.error.message}"
        header = f"slots ({self.model_name}):" if self.model_name else "slots:"
        return "\n".join([header, *(slot.render() for slot in self.slots)])


def _slots_from(status: int, text: str, model: str | None) -> SlotsReport:
    """Build a SlotsReport from a /slots response (error body or list of slots)."""
    if status != 200:
        try:
            return SlotsReport.model_validate(json.loads(text))
        except ValueError as err:
            raise ServerError(f"HTTP {status}: {text.strip()}") from err
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError("expected a list of slots")
        return SlotsReport(model_name=model, slots=[Slot.model_validate(item) for item in items])
    except (ValueError, ValidationError) as err:
        raise ServerError(f"failed to parse slots response: {err}") from err


def get_slots(server: str | None = None, model: str | None = None) -> SlotsReport:
    """Query GET /slots and return the validated SlotsReport model."""
    params = {"model": model} if model is not None else None
    status, text = fetch(resolve_server_url(server), "/slots", params=params)
    return _slots_from(status, text, model)


async def aget_slots(server: str | None = None, model: str | None = None) -> SlotsReport:
    """Async version of get_slots()."""
    params = {"model": model} if model is not None else None
    status, text = await afetch(resolve_server_url(server), "/slots", params=params)
    return _slots_from(status, text, model)
