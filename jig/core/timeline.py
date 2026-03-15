"""TimelineController — central timeline state with Qt signals and playback."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal, Slot

# Playback speed tiers for +/- key cycling
SPEED_TIERS: list[float] = [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0]
SPEED_MAX_SENTINEL: float = -1.0  # means "advance one data step per frame"

_PLAYBACK_INTERVAL_MS = 16  # ~60 fps


class TimelineController(QObject):
    """Owns the current playback time, range, and playback engine.

    Signals:
        time_changed(float): current time moved (scrub or playback tick).
        range_changed(float, float): data time range changed.
        playback_changed(bool): play/pause state toggled.
        playback_rate_changed(float): speed multiplier changed.
    """

    time_changed = Signal(float)
    range_changed = Signal(float, float)
    playback_changed = Signal(bool)
    playback_rate_changed = Signal(float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._current_time: float = 0.0
        self._t_min: float = 0.0
        self._t_max: float = 0.0
        self._playing: bool = False
        self._rate: float = 1.0
        self._step_size: float = 0.001  # default 1 ms

        # Playback timer
        self._timer = QTimer(self)
        self._timer.setInterval(_PLAYBACK_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

        # Wall-clock tracker for accurate dt
        self._elapsed = QElapsedTimer()

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

    @property
    def playback_rate(self) -> float:
        return self._rate

    @property
    def step_size(self) -> float:
        return self._step_size

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

    def set_step_size(self, step: float) -> None:
        """Set the step size (typically median sample interval)."""
        if step > 0:
            self._step_size = step

    # -- Playback control ----------------------------------------------------

    def play(self, rate: float | None = None) -> None:
        """Start advancing current_time at the given rate."""
        if rate is not None:
            self.set_playback_rate(rate)
        if not self._playing:
            # If at the end, wrap to start
            if self._current_time >= self._t_max and self.duration > 0:
                self._current_time = self._t_min
                self.time_changed.emit(self._current_time)
            self._playing = True
            self._elapsed.start()
            self._timer.start()
            self.playback_changed.emit(True)

    def pause(self) -> None:
        """Stop advancing current_time."""
        if self._playing:
            self._playing = False
            self._timer.stop()
            self.playback_changed.emit(False)

    def toggle_play_pause(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    # Keep backward compat with old API
    def set_playing(self, playing: bool) -> None:
        if playing:
            self.play()
        else:
            self.pause()

    def toggle_playing(self) -> None:
        self.toggle_play_pause()

    def set_playback_rate(self, rate: float) -> None:
        if rate != self._rate:
            self._rate = rate
            self.playback_rate_changed.emit(rate)

    def speed_up(self) -> None:
        """Move to the next higher speed tier."""
        idx = _find_tier_index(self._rate)
        if idx < len(SPEED_TIERS) - 1:
            self.set_playback_rate(SPEED_TIERS[idx + 1])

    def speed_down(self) -> None:
        """Move to the next lower speed tier."""
        idx = _find_tier_index(self._rate)
        if idx > 0:
            self.set_playback_rate(SPEED_TIERS[idx - 1])

    # -- Seek / step ---------------------------------------------------------

    def seek(self, t: float) -> None:
        """Immediately jump to time t."""
        self.set_time(t)

    def go_to_start(self) -> None:
        self.set_time(self._t_min)

    def go_to_end(self) -> None:
        self.pause()
        self.set_time(self._t_max)

    def step_forward(self) -> None:
        """Advance by one step."""
        self.set_time(self._current_time + self._step_size)

    def step_backward(self) -> None:
        """Retreat by one step."""
        self.set_time(self._current_time - self._step_size)

    def jump_forward(self, dt: float = 1.0) -> None:
        """Jump forward by dt seconds."""
        self.set_time(self._current_time + dt)

    def jump_backward(self, dt: float = 1.0) -> None:
        """Jump backward by dt seconds."""
        self.set_time(self._current_time - dt)

    # -- Internal ------------------------------------------------------------

    def _on_tick(self) -> None:
        """Called by the playback QTimer at ~60 fps."""
        dt_ns = self._elapsed.nsecsElapsed()
        self._elapsed.restart()
        dt_s = dt_ns / 1e9

        new_t = self._current_time + dt_s * self._rate
        if new_t >= self._t_max:
            new_t = self._t_max
            self.set_time(new_t)
            self.pause()
            return
        self.set_time(new_t)


def _find_tier_index(rate: float) -> int:
    """Find the closest speed tier index for the given rate."""
    best = 0
    best_diff = abs(rate - SPEED_TIERS[0])
    for i, tier in enumerate(SPEED_TIERS):
        diff = abs(rate - tier)
        if diff < best_diff:
            best = i
            best_diff = diff
    return best
