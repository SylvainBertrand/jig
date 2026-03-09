"""DataStore — in-memory container for all loaded data in a session."""

from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QObject, Signal

from jig.core.types import TimeSeries, TopicInfo


class DataStore(QObject):
    """Holds scalar time series and non-scalar messages for one session.

    Thread safety: ``add_topic`` / ``add_series`` / ``add_message`` emit Qt
    signals.  When called from a worker thread the signals are delivered to
    the main thread via ``Qt.QueuedConnection`` (automatic for cross-thread
    QObject signals).

    Signals:
        topic_added(TopicInfo): a new topic has been registered.
        series_added(str): a new scalar series path has been added.
        data_changed(): bulk notification that data has been updated.
    """

    topic_added = Signal(object)   # TopicInfo
    series_added = Signal(str)     # full series path
    data_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._topics: dict[str, TopicInfo] = {}
        self._series: dict[str, TimeSeries] = {}  # keyed by full path
        self._messages: dict[str, list[tuple[float, Any]]] = {}  # topic -> [(t, msg)]
        self._time_range: tuple[float, float] = (0.0, 0.0)

    # -- Topics --------------------------------------------------------------

    @property
    def topics(self) -> dict[str, TopicInfo]:
        return dict(self._topics)

    def add_topic(self, info: TopicInfo) -> None:
        self._topics[info.name] = info
        self.topic_added.emit(info)

    # -- Scalar series -------------------------------------------------------

    @property
    def series_names(self) -> list[str]:
        return list(self._series.keys())

    def add_series(self, path: str, timestamps: np.ndarray, values: np.ndarray) -> None:
        """Register a scalar time series (e.g. '/joint_states/position[0]')."""
        self._series[path] = TimeSeries(name=path, timestamps=timestamps, values=values)
        self._update_time_range(timestamps)
        self.series_added.emit(path)

    def get_series(self, path: str) -> TimeSeries | None:
        return self._series.get(path)

    def get_scalar_at(self, path: str, t: float) -> float:
        """Return the scalar value of a series at time t."""
        ts = self._series.get(path)
        if ts is None:
            return 0.0
        return ts.value_at(t)

    # -- Non-scalar messages (images, point clouds, etc.) --------------------

    def add_message(self, topic: str, timestamp: float, message: Any) -> None:
        """Append a non-scalar message for a topic."""
        if topic not in self._messages:
            self._messages[topic] = []
        self._messages[topic].append((timestamp, message))
        self._update_time_range(np.array([timestamp]))

    def get_message_at(self, topic: str, t: float) -> tuple[float, Any] | None:
        """Return the message at or just before time t."""
        msgs = self._messages.get(topic)
        if not msgs:
            return None
        # Messages are appended in order; binary search
        timestamps = [m[0] for m in msgs]
        idx = int(np.searchsorted(timestamps, t, side="right")) - 1
        idx = max(0, min(idx, len(msgs) - 1))
        return msgs[idx]

    def get_message_timestamps(self, topic: str) -> list[float]:
        msgs = self._messages.get(topic)
        if not msgs:
            return []
        return [m[0] for m in msgs]

    def message_topics(self) -> list[str]:
        return list(self._messages.keys())

    # -- Time range ----------------------------------------------------------

    @property
    def time_range(self) -> tuple[float, float]:
        return self._time_range

    def _update_time_range(self, timestamps: np.ndarray) -> None:
        if len(timestamps) == 0:
            return
        new_min = float(timestamps.min())
        new_max = float(timestamps.max())
        cur_min, cur_max = self._time_range
        if cur_min == cur_max == 0.0:
            self._time_range = (new_min, new_max)
        else:
            self._time_range = (min(cur_min, new_min), max(cur_max, new_max))
