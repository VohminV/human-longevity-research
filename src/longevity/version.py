"""Version registry for the platform.

Модель и данные версионируются отдельно (см. docs/ARCHITECTURE.md).
Этот модуль — источник версии для экспериментов и checkpoints.
"""

from __future__ import annotations

MODEL_VERSION = "0.2.0"
DATA_VERSION = "0.1.0"


def version_info() -> str:
    """Human-readable version string: model data."""
    return f"model={MODEL_VERSION} data={DATA_VERSION}"