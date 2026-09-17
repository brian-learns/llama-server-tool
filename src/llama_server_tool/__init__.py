# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""llama_server_tool: administer a local llama-server, from the CLI or as a Python API.

The API functions return validated pydantic models; well-formed API error bodies
(e.g. a 503 while the model loads) come back as models with `.error` set, while
transport and parse failures raise `ServerError`.
"""

from .health import Health, check_health
from .metrics import MetricsReport, get_metrics
from .models import ModelList, get_models
from .props import Props, get_props
from .server import ApiError, ServerError
from .slots import Slot, SlotsReport, get_slots

__all__ = [
    "ApiError",
    "Health",
    "MetricsReport",
    "ModelList",
    "Props",
    "ServerError",
    "Slot",
    "SlotsReport",
    "check_health",
    "get_metrics",
    "get_models",
    "get_props",
    "get_slots",
]
