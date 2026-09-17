# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 llama_server_tool creators and contributors

"""llama_server_tool: administer a local llama-server, from the CLI or as a Python API.

The API functions return validated pydantic models; well-formed API error bodies
(e.g. a 503 while the model loads) come back as models with `.error` set, while
transport and parse failures raise `ServerError`.
"""

from .health import Health, aget_health, check_health
from .metrics import MetricsReport, aget_metrics, get_metrics
from .models import ModelList, ModelStatus, aget_models, get_models
from .props import Props, aget_props, get_props
from .server import ApiError, ServerError
from .slots import Slot, SlotsReport, aget_slots, get_slots
from .status import StatusBlock, StatusReport, get_status

__all__ = [
    "ApiError",
    "Health",
    "MetricsReport",
    "ModelList",
    "ModelStatus",
    "Props",
    "ServerError",
    "Slot",
    "SlotsReport",
    "StatusBlock",
    "StatusReport",
    "aget_health",
    "aget_metrics",
    "aget_models",
    "aget_props",
    "aget_slots",
    "check_health",
    "get_metrics",
    "get_models",
    "get_props",
    "get_slots",
    "get_status",
]
