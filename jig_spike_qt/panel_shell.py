"""Main window with dockable panel system and global timeline."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSlider,
    QToolBar,
    QWidget,
)

from jig_spike_qt.data_store import DataStore


class MainWindow(QMainWindow):
    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self.data_store = data_store
        self._panel_count = 0
        self.setWindowTitle("Jig \u2014 Qt6 Spike")
        self.resize(1400, 900)

        # Hide central widget so dock widgets fill the space
        central = QWidget()
        central.setMaximumHeight(0)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_timeline()

        self.data_store.timeline_changed.connect(self._on_timeline_changed)

    def _build_menu(self):
        menu_bar = self.menuBar()
        panel_menu = menu_bar.addMenu("Panels")
        for name in ("3D Viewer", "Chart", "Image"):
            action = panel_menu.addAction(f"Add {name}")
            action.triggered.connect(lambda checked, n=name: self.add_panel(n))

    def _build_timeline(self):
        toolbar = QToolBar("Timeline")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.addWidget(QLabel("Time:"))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        steps = int(self.data_store.t_max * 1000)
        self.slider.setRange(0, max(steps, 1))
        self.slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self.slider, stretch=1)

        self.time_label = QLabel("0.000 s")
        self.time_label.setMinimumWidth(80)
        layout.addWidget(self.time_label)

        toolbar.addWidget(container)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, toolbar)

    def _on_slider(self, value: int):
        t = value / 1000.0
        self.data_store.set_time(t)

    def _on_timeline_changed(self, t: float):
        self.time_label.setText(f"{t:.3f} s")
        self.slider.blockSignals(True)
        self.slider.setValue(int(t * 1000))
        self.slider.blockSignals(False)

    def add_panel(self, panel_type: str):
        # Lazy imports to avoid circular deps
        from jig_spike_qt.viewer_3d import Viewer3DPanel
        from jig_spike_qt.chart_panel import ChartPanel
        from jig_spike_qt.image_panel import ImagePanel

        self._panel_count += 1
        label = f"{panel_type} #{self._panel_count}"

        if panel_type == "3D Viewer":
            widget = Viewer3DPanel(self.data_store)
        elif panel_type == "Chart":
            widget = ChartPanel(self.data_store)
        elif panel_type == "Image":
            widget = ImagePanel(self.data_store)
        else:
            return

        dock = QDockWidget(label, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
