"""TimelineController — central timeline state with Qt signals."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class TimelineController(QObject):
    """Owns the current playback time and range. Single source of truth.

    Signals:
        time_changed(float): emitted when the current time changes.
        range_changed(float, float): emitted when the time range changes.
        playback_changed(bool): emitted when play/pause state changes.
    """

    time_changed = Signal(float)
    range_changed = Signal(float, float)
    playback_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_time: float = 0.0
        self._t_min: float = 0.0
        self._t_max: float = 0.0
        self._playing: bool = False

    # -- Properties ----------------------------------------------------------

    @property
    def current_time(self) -> float:
        return self._current_time

    @property
    def t_min(self) -> float:
        return self._t_min

    @property
    def t_max(self) -> float:
        return self._t_max

    @property
    def duration(self) -> float:
        return self._t_max - self._t_min

    @property
    def playing(self) -> bool:
        return self._playing

    # -- Mutators ------------------------------------------------------------

    @Slot(float)
    def set_time(self, t: float) -> None:
        """Set current time, clamping to range."""
        t = max(self._t_min, min(t, self._t_max))
        if t != self._current_time:
            self._current_time = t
            self.time_changed.emit(t)

    def set_range(self, t_min: float, t_max: float) -> None:
        """Set the valid time range (typically from data extent)."""
        self._t_min = t_min
        self._t_max = max(t_min, t_max)
        self._current_time = max(self._t_min, min(self._current_time, self._t_max))
        self.range_changed.emit(self._t_min, self._t_max)

    def set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.playback_changed.emit(playing)

    def toggle_playing(self) -> None:
        self.set_playing(not self._playing)
