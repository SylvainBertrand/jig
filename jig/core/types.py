"""Shared types used across Jig."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

import numpy as np


class SessionType(Enum):
    """Type of data session."""

    LOG = auto()
    REMOTE = auto()


@dataclass(frozen=True)
class TopicInfo:
    """Metadata for a single topic in the DataStore."""

    name: str
    message_type: str  # e.g. "sensor_msgs/JointState"
    message_count: int = 0
    fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TimeSeries:
    """A named scalar time series backed by numpy arrays."""

    name: str
    timestamps: np.ndarray  # shape (N,), float64 seconds
    values: np.ndarray  # shape (N,), float64

    def __len__(self) -> int:
        return len(self.timestamps)

    def value_at(self, t: float) -> float:
        """Return value at or just before time t via binary search."""
        if len(self.timestamps) == 0:
            return 0.0
        idx = int(np.searchsorted(self.timestamps, t, side="right")) - 1
        idx = max(0, min(idx, len(self.timestamps) - 1))
        return float(self.values[idx])
