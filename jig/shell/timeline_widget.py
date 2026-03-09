"""TimelineWidget — global scrub bar at the bottom of the window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from jig.core.timeline import TimelineController

_SLIDER_RESOLUTION = 10_000  # ticks across the full range


class TimelineWidget(QWidget):
    """Horizontal slider + time label that drives a TimelineController."""

    def __init__(self, timeline: TimelineController, parent: QWidget | None = None):
        super().__init__(parent)
        self._timeline = timeline

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)

        layout.addWidget(QLabel("Time:"))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SLIDER_RESOLUTION)
        self._slider.valueChanged.connect(self._on_slider_moved)
        layout.addWidget(self._slider, stretch=1)

        self._time_label = QLabel("0.000 s")
        self._time_label.setMinimumWidth(90)
        layout.addWidget(self._time_label)

        self._timeline.time_changed.connect(self._on_time_changed)
        self._timeline.range_changed.connect(self._on_range_changed)

    # -- Slider → timeline ---------------------------------------------------

    def _on_slider_moved(self, value: int) -> None:
        frac = value / _SLIDER_RESOLUTION
        t = self._timeline.t_min + frac * self._timeline.duration
        self._timeline.set_time(t)

    # -- Timeline → slider ---------------------------------------------------

    def _on_time_changed(self, t: float) -> None:
        self._time_label.setText(f"{t:.3f} s")
        dur = self._timeline.duration
        if dur > 0:
            frac = (t - self._timeline.t_min) / dur
            self._slider.blockSignals(True)
            self._slider.setValue(int(frac * _SLIDER_RESOLUTION))
            self._slider.blockSignals(False)

    def _on_range_changed(self, t_min: float, t_max: float) -> None:
        self._time_label.setText(f"{self._timeline.current_time:.3f} s")
