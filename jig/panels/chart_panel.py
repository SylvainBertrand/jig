"""ChartPanel — time-series chart using pyqtgraph."""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jig.core.app_context import AppContext
from jig.core.signal import SignalRef
from jig.panels.base import PanelBase
from jig.panels.registry import PanelRegistry
from jig.shell.variable_browser import SIGNAL_MIME_TYPE

try:
    import pyqtgraph as pg

    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45",
    "#fabebe", "#008080", "#e6beff", "#9a6324",
]


class _SignalChip(QWidget):
    """Small colored tag representing a plotted signal, with a close button."""

    def __init__(
        self, ref: SignalRef, color: str, on_remove, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.ref = ref
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 2, 1)
        layout.setSpacing(2)

        dot = QLabel("\u25cf")
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        layout.addWidget(dot)

        label = QLabel(ref.field)
        label.setStyleSheet("font-size: 11px;")
        label.setToolTip(ref.full_path)
        layout.addWidget(label)

        close_btn = QPushButton("\u00d7")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 12px; color: #888; }"
            "QPushButton:hover { color: #e00; }"
        )
        close_btn.setToolTip("Remove signal")
        close_btn.clicked.connect(lambda: on_remove(ref))
        layout.addWidget(close_btn)

        self.setStyleSheet(
            "background: #2a2a2e; border-radius: 3px; margin: 1px;"
        )


@PanelRegistry.register
class ChartPanel(PanelBase):
    panel_type_name = "Chart"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.setMinimumSize(400, 250)
        self._signals: list[SignalRef] = []
        self._plot_items: list = []
        self._colors: list[str] = []
        self._drop_highlight = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Signal chips header
        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(4, 2, 4, 2)
        self._chips_layout.setSpacing(2)
        self._chips_layout.addStretch()
        layout.addWidget(self._chips_widget)

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
        layout.addWidget(self._plot_widget, stretch=1)
        layout.addWidget(self._status_label)

        # Time cursor
        self._cursor = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen("w", width=2, style=pg.QtCore.Qt.PenStyle.DashLine),
        )
        self._plot_widget.addItem(self._cursor)

        # Crosshair for value readout
        self._vline = pg.InfiniteLine(angle=90, pen=pg.mkPen("#555", width=1))
        self._hline = pg.InfiniteLine(angle=0, pen=pg.mkPen("#555", width=1))
        self._plot_widget.addItem(self._vline, ignoreBounds=True)
        self._plot_widget.addItem(self._hline, ignoreBounds=True)
        self._vline.setVisible(False)
        self._hline.setVisible(False)

        # Mouse move for crosshair
        self._proxy = pg.SignalProxy(
            self._plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

        # Disable pyqtgraph's built-in context menu, use ours instead
        self._plot_widget.plotItem.setMenuEnabled(False)
        self._plot_widget.setContextMenuPolicy(
            pg.QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._plot_widget.customContextMenuRequested.connect(self._show_context_menu)

        # Accept drops
        self.setAcceptDrops(True)

        # Auto-add first 4 joint series if data is already loaded
        self._auto_populate()

    # -- Signal management ---------------------------------------------------

    def _auto_populate(self) -> None:
        ds = self.ctx.active_data_store
        if ds is None:
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
        # Don't add duplicates
        if ref in self._signals:
            return
        ds = self.ctx.active_data_store
        if ds is None:
            return
        series = ds.get_series(ref.full_path)
        if series is None:
            return

        color = COLORS[len(self._signals) % len(COLORS)]
        item = self._plot_widget.plot(
            series.timestamps,
            series.values,
            pen=pg.mkPen(color, width=1),
            name=ref.field,
        )
        self._signals.append(ref)
        self._plot_items.append(item)
        self._colors.append(color)
        self._rebuild_chips()

    def remove_signal(self, ref: SignalRef) -> None:
        if not HAS_PYQTGRAPH:
            return
        if ref not in self._signals:
            return
        idx = self._signals.index(ref)
        self._plot_widget.removeItem(self._plot_items[idx])
        del self._signals[idx]
        del self._plot_items[idx]
        del self._colors[idx]
        self._rebuild_chips()
        # Update legend
        self._plot_widget.plotItem.legend.clear()
        for sig, plot_item, col in zip(self._signals, self._plot_items, self._colors):
            self._plot_widget.plotItem.legend.addItem(plot_item, sig.field)

    def remove_all_signals(self) -> None:
        for item in self._plot_items:
            self._plot_widget.removeItem(item)
        self._signals.clear()
        self._plot_items.clear()
        self._colors.clear()
        self._rebuild_chips()
        self._plot_widget.plotItem.legend.clear()

    def _rebuild_chips(self) -> None:
        """Rebuild the signal chips header."""
        # Remove old chips (keep the stretch at the end)
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for ref, color in zip(self._signals, self._colors):
            chip = _SignalChip(ref, color, self.remove_signal)
            self._chips_layout.insertWidget(
                self._chips_layout.count() - 1, chip
            )

    # -- Context menu --------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)

        # Add signal submenu
        add_menu = menu.addMenu("Add Signal...")
        ds = self.ctx.active_data_store
        if ds is not None:
            for name in ds.series_names:
                parts = name.rsplit("/", 1)
                if len(parts) == 2:
                    ref = SignalRef(topic=parts[0], field=parts[1])
                    if ref not in self._signals:
                        action = add_menu.addAction(name)
                        action.triggered.connect(
                            lambda checked, r=ref: self.add_signal(r)
                        )

        # Quick plot dialog
        menu.addAction("Quick Plot... (Ctrl+P)", self._open_quick_plot)

        menu.addSeparator()
        menu.addAction("Remove All Signals", self.remove_all_signals)
        menu.addSeparator()
        menu.addAction("Auto-scale Y Axis", self._auto_scale_y)
        menu.addAction("Reset Zoom", self._reset_zoom)

        menu.exec(self._plot_widget.mapToGlobal(pos))

    def _auto_scale_y(self) -> None:
        if HAS_PYQTGRAPH:
            self._plot_widget.enableAutoRange(axis="y")

    def _reset_zoom(self) -> None:
        if HAS_PYQTGRAPH:
            self._plot_widget.enableAutoRange()

    def _open_quick_plot(self) -> None:
        from jig.shell.quick_plot_dialog import QuickPlotDialog

        ds = self.ctx.active_data_store
        if ds is None:
            return
        dlg = QuickPlotDialog(ds, parent=self)
        if dlg.exec():
            for path in dlg.selected_paths():
                parts = path.rsplit("/", 1)
                if len(parts) == 2:
                    self.add_signal(SignalRef(topic=parts[0], field=parts[1]))

    # -- Crosshair / cursor readout -----------------------------------------

    def _on_mouse_moved(self, evt) -> None:
        pos = evt[0]
        if not self._plot_widget.sceneBoundingRect().contains(pos):
            self._vline.setVisible(False)
            self._hline.setVisible(False)
            return

        mouse_point = self._plot_widget.plotItem.vb.mapSceneToView(pos)
        x, y = mouse_point.x(), mouse_point.y()
        self._vline.setPos(x)
        self._hline.setPos(y)
        self._vline.setVisible(True)
        self._hline.setVisible(True)

        # Build readout
        ds = self.ctx.active_data_store
        if ds is None:
            return
        parts = [f"t={x:.3f}s"]
        for ref in self._signals:
            val = ds.get_scalar_at(ref.full_path, x)
            parts.append(f"{ref.field}={val:.4f}")
        self._status_label.setText("  |  ".join(parts))

    # -- Drag and drop -------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(SIGNAL_MIME_TYPE):
            event.acceptProposedAction()
            self._set_drop_highlight(True)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasFormat(SIGNAL_MIME_TYPE):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_highlight(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drop_highlight(False)
        data = event.mimeData().data(SIGNAL_MIME_TYPE)
        if not data:
            return
        for path in bytes(data).decode("utf-8").splitlines():
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                self.add_signal(SignalRef(topic=parts[0], field=parts[1]))
        event.acceptProposedAction()

    def _set_drop_highlight(self, on: bool) -> None:
        self._drop_highlight = on
        if on:
            self.setStyleSheet("ChartPanel { border: 2px solid #4488ff; }")
        else:
            self.setStyleSheet("")

    # -- PanelBase interface -------------------------------------------------

    def on_time_changed(self, t: float) -> None:
        if not HAS_PYQTGRAPH:
            return
        t0 = time.perf_counter()
        self._cursor.setValue(t)
        dt_ms = (time.perf_counter() - t0) * 1000
        # Don't overwrite the crosshair readout if mouse is over the chart
        if not self._vline.isVisible():
            self._status_label.setText(f"Chart update: {dt_ms:.2f} ms")

    def get_state(self) -> dict[str, Any]:
        return {
            "signals": [
                {"topic": s.topic, "field": s.field} for s in self._signals
            ],
        }

    def set_state(self, state: dict[str, Any]) -> None:
        for s in state.get("signals", []):
            self.add_signal(SignalRef(topic=s["topic"], field=s["field"]))
