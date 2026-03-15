"""TimelineWidget — full transport bar at the bottom of the window.

Layout:
  [|<] [<] [>/||] [>|] [>>]  [1.0x v]  ---o-----------  00:03.245 / 00:45.120
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from jig.core.timeline import SPEED_TIERS, TimelineController

_SLIDER_RESOLUTION = 10_000


def _format_time(t: float) -> str:
    """Format seconds as MM:SS.mmm or HH:MM:SS.mmm."""
    if t < 0:
        t = 0.0
    ms = int((t % 1) * 1000)
    total_s = int(t)
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{m:02d}:{s:02d}.{ms:03d}"


def _make_transport_btn(text: str, tooltip: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(28, 24)
    btn.setToolTip(tooltip)
    btn.setObjectName("transportBtn")
    return btn


class TimelineWidget(QWidget):
    """Full transport bar: buttons, speed selector, scrub slider, time display."""

    def __init__(self, timeline: TimelineController, parent: QWidget | None = None):
        super().__init__(parent)
        self._timeline = timeline

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(4)

        # -- Transport buttons --
        self._btn_start = _make_transport_btn("\u23ee", "Go to start (Home)")
        self._btn_step_back = _make_transport_btn("\u23f4", "Step back (Left)")
        self._btn_play = _make_transport_btn("\u25b6", "Play / Pause (Space)")
        self._btn_step_fwd = _make_transport_btn("\u23f5", "Step forward (Right)")
        self._btn_end = _make_transport_btn("\u23ed", "Go to end (End)")

        self._btn_start.clicked.connect(self._timeline.go_to_start)
        self._btn_step_back.clicked.connect(self._timeline.step_backward)
        self._btn_play.clicked.connect(self._timeline.toggle_play_pause)
        self._btn_step_fwd.clicked.connect(self._timeline.step_forward)
        self._btn_end.clicked.connect(self._timeline.go_to_end)

        for btn in (self._btn_start, self._btn_step_back, self._btn_play,
                    self._btn_step_fwd, self._btn_end):
            layout.addWidget(btn)

        layout.addSpacing(8)

        # -- Speed selector --
        self._speed_combo = QComboBox()
        self._speed_combo.setFixedWidth(70)
        self._speed_combo.setToolTip("Playback speed (+/-)")
        for tier in SPEED_TIERS:
            self._speed_combo.addItem(f"{tier}x", tier)
        self._speed_combo.setCurrentIndex(SPEED_TIERS.index(1.0))
        self._speed_combo.currentIndexChanged.connect(self._on_speed_selected)
        layout.addWidget(self._speed_combo)

        layout.addSpacing(8)

        # -- Scrub slider --
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SLIDER_RESOLUTION)
        self._slider.valueChanged.connect(self._on_slider_moved)
        layout.addWidget(self._slider, stretch=1)

        layout.addSpacing(8)

        # -- Time display --
        self._time_label = QLabel("00:00.000 / 00:00.000")
        self._time_label.setObjectName("timeDisplay")
        self._time_label.setMinimumWidth(170)
        self._time_label.setStyleSheet(
            "font-family: 'Consolas', 'SF Mono', 'Ubuntu Mono', monospace; font-size: 12px;"
        )
        layout.addWidget(self._time_label)

        # -- Connect signals --
        self._timeline.time_changed.connect(self._on_time_changed)
        self._timeline.range_changed.connect(self._on_range_changed)
        self._timeline.playback_changed.connect(self._on_playback_changed)
        self._timeline.playback_rate_changed.connect(self._on_rate_changed)

    # -- Slider → timeline ---------------------------------------------------

    def _on_slider_moved(self, value: int) -> None:
        frac = value / _SLIDER_RESOLUTION
        t = self._timeline.t_min + frac * self._timeline.duration
        self._timeline.set_time(t)

    # -- Speed combo → timeline ----------------------------------------------

    def _on_speed_selected(self, index: int) -> None:
        rate = self._speed_combo.itemData(index)
        if rate is not None:
            self._timeline.set_playback_rate(rate)

    # -- Timeline → UI -------------------------------------------------------

    def _on_time_changed(self, t: float) -> None:
        rel = t - self._timeline.t_min
        dur = self._timeline.duration
        self._time_label.setText(
            f"{_format_time(rel)} / {_format_time(dur)}"
        )
        self._time_label.setToolTip(f"Absolute: {t:.6f} s")
        if dur > 0:
            frac = (t - self._timeline.t_min) / dur
            self._slider.blockSignals(True)
            self._slider.setValue(int(frac * _SLIDER_RESOLUTION))
            self._slider.blockSignals(False)

    def _on_range_changed(self, t_min: float, t_max: float) -> None:
        rel = self._timeline.current_time - t_min
        dur = t_max - t_min
        self._time_label.setText(
            f"{_format_time(rel)} / {_format_time(dur)}"
        )

    def _on_playback_changed(self, playing: bool) -> None:
        if playing:
            self._btn_play.setText("\u23f8")
            self._btn_play.setToolTip("Pause (Space)")
        else:
            self._btn_play.setText("\u25b6")
            self._btn_play.setToolTip("Play (Space)")

    def _on_rate_changed(self, rate: float) -> None:
        for i in range(self._speed_combo.count()):
            if self._speed_combo.itemData(i) == rate:
                self._speed_combo.blockSignals(True)
                self._speed_combo.setCurrentIndex(i)
                self._speed_combo.blockSignals(False)
                return
