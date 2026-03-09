"""ChartPanel — time-series chart using pyqtgraph."""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from jig.core.app_context import AppContext
from jig.core.signal import SignalRef
from jig.panels.base import PanelBase
from jig.panels.registry import PanelRegistry

try:
    import pyqtgraph as pg

    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#bfef45"]


@PanelRegistry.register
class ChartPanel(PanelBase):
    panel_type_name = "Chart"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.setMinimumSize(400, 250)
        self._signals: list[SignalRef] = []
        self._plot_items: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; padding: 2px;")

        if not HAS_PYQTGRAPH:
            layout.addWidget(QLabel("pyqtgraph not installed"))
            layout.addWidget(self._status_label)
            return

        pg.setConfigOptions(antialias=False, useOpenGL=False)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("bottom", "Time", units="s")
        self._plot_widget.setLabel("left", "Value")
        self._plot_widget.addLegend(offset=(10, 10))
        layout.addWidget(self._plot_widget)
        layout.addWidget(self._status_label)

        self._cursor = pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen("w", width=2, style=pg.QtCore.Qt.PenStyle.DashLine),
        )
        self._plot_widget.addItem(self._cursor)

        # Right-click to add signals
        self._plot_widget.setContextMenuPolicy(
            pg.QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._plot_widget.customContextMenuRequested.connect(self._show_add_signal_menu)

        # Accept drops from TopicBrowser
        self.setAcceptDrops(True)

        # Auto-add first 4 joint series if data is already loaded
        self._auto_populate()

    def _auto_populate(self) -> None:
        ds = self.ctx.active_data_store
        if ds is None:
            # Data not loaded yet — connect to data_changed for when it arrives
            for session in self.ctx.sessions:
                session.data_store.data_changed.connect(self._on_data_changed)
            return
        names = ds.series_names
        for name in names[:4]:
            parts = name.rsplit("/", 1)
            if len(parts) == 2:
                self.add_signal(SignalRef(topic=parts[0], field=parts[1]))

    def _on_data_changed(self) -> None:
        if not self._signals:
            self._auto_populate()

    def add_signal(self, ref: SignalRef) -> None:
        if not HAS_PYQTGRAPH:
            return
        ds = self.ctx.active_data_store
        if ds is None:
            return
        series = ds.get_series(ref.full_path)
        if series is None:
            return

        color = COLORS[len(self._signals) % len(COLORS)]
        item = self._plot_widget.plot(
            series.timestamps, series.values,
            pen=pg.mkPen(color, width=1),
            name=ref.field,
        )
        self._signals.append(ref)
        self._plot_items.append(item)

    def _show_add_signal_menu(self, pos) -> None:
        ds = self.ctx.active_data_store
        if ds is None:
            return
        menu = QMenu(self)
        for name in ds.series_names:
            parts = name.rsplit("/", 1)
            if len(parts) == 2:
                ref = SignalRef(topic=parts[0], field=parts[1])
                action = menu.addAction(name)
                action.triggered.connect(lambda checked, r=ref: self.add_signal(r))
        menu.exec(self._plot_widget.mapToGlobal(pos))

    # -- Drag and drop -------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        from jig.shell.topic_browser import SIGNAL_MIME_TYPE

        if event.mimeData().hasFormat(SIGNAL_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        from jig.shell.topic_browser import SIGNAL_MIME_TYPE

        data = event.mimeData().data(SIGNAL_MIME_TYPE)
        if not data:
            return
        for path in bytes(data).decode("utf-8").splitlines():
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                self.add_signal(SignalRef(topic=parts[0], field=parts[1]))
        event.acceptProposedAction()

    # -- PanelBase interface -------------------------------------------------

    def on_time_changed(self, t: float) -> None:
        if not HAS_PYQTGRAPH:
            return
        t0 = time.perf_counter()
        self._cursor.setValue(t)
        dt_ms = (time.perf_counter() - t0) * 1000
        self._status_label.setText(f"Chart update: {dt_ms:.2f} ms")

    def get_state(self) -> dict[str, Any]:
        return {
            "signals": [{"topic": s.topic, "field": s.field} for s in self._signals],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        for s in state.get("signals", []):
            self.add_signal(SignalRef(topic=s["topic"], field=s["field"]))
