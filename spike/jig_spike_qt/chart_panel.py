"""Time-series chart panel using pyqtgraph."""

import time

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jig_spike_qt.data_store import DataStore

try:
    import pyqtgraph as pg

    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False

COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231"]


class ChartPanel(QWidget):
    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self.data_store = data_store
        self.setMinimumSize(400, 250)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 2px;")

        if not HAS_PYQTGRAPH:
            layout.addWidget(QLabel("pyqtgraph not installed"))
            layout.addWidget(self.status_label)
            return

        pg.setConfigOptions(antialias=False, useOpenGL=False)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Position", units="rad")
        self.plot_widget.addLegend(offset=(10, 10))
        layout.addWidget(self.plot_widget)
        layout.addWidget(self.status_label)

        # Plot first 4 joints
        ts = data_store.joint_timestamps
        pos = data_store.joint_positions
        num_traces = min(4, pos.shape[1]) if len(pos) > 0 else 0
        for i in range(num_traces):
            self.plot_widget.plot(
                ts,
                pos[:, i],
                pen=pg.mkPen(COLORS[i], width=1),
                name=f"joint{i + 1}",
            )

        # Vertical cursor synced to timeline
        self.cursor = pg.InfiniteLine(
            pos=0,
            angle=90,
            pen=pg.mkPen("w", width=2, style=pg.QtCore.Qt.PenStyle.DashLine),
        )
        self.plot_widget.addItem(self.cursor)

        self.data_store.timeline_changed.connect(self._on_timeline)

    def _on_timeline(self, t: float):
        if not HAS_PYQTGRAPH:
            return
        t0 = time.perf_counter()
        self.cursor.setValue(t)
        dt_ms = (time.perf_counter() - t0) * 1000
        self.status_label.setText(f"Chart update: {dt_ms:.2f} ms")
