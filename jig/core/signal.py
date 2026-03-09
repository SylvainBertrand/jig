"""SignalRef — a pointer to a specific data series in a DataStore."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalRef:
    """Reference to a scalar signal within a session's DataStore.

    Examples:
        SignalRef(topic="/joint_states", field="position[0]")
        SignalRef(topic="/imu/data", field="angular_velocity.x")
    """

    topic: str
    field: str

    @property
    def full_path(self) -> str:
        return f"{self.topic}/{self.field}"

    def __str__(self) -> str:
        return self.full_path
