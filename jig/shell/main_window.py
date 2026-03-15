"""JigWindow — main application window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QStatusBar,
    QToolBar,
    QWidget,
)

from jig.core.app_context import AppContext
from jig.core.signal import SignalRef
from jig.panels.registry import PanelRegistry
from jig.sessions.log_session import LogSession
from jig.shell.dock_manager import DockManager
from jig.shell.timeline_widget import TimelineWidget
from jig.shell.variable_browser import VariableBrowser


class JigWindow(QMainWindow):
    """Top-level window with menu bar, dock area, sidebar, and timeline."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Jig")
        self.resize(1400, 900)

        # Dock manager (PyQtAds CDockManager becomes the central widget)
        self.dock_manager = DockManager(self, ctx)
        self.setCentralWidget(self.dock_manager.ads_dock_manager)

        # Variable browser sidebar
        self._var_browser = VariableBrowser()
        self._var_browser.set_double_click_callback(self._on_signal_double_clicked)
        sidebar_dock = QDockWidget("Variables", self)
        sidebar_dock.setWidget(self._var_browser)
        sidebar_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, sidebar_dock)

        # Timeline at bottom (toolbar, not floatable — stays pinned)
        self._timeline_widget = TimelineWidget(ctx.timeline)
        timeline_toolbar = QToolBar("Timeline")
        timeline_toolbar.setMovable(False)
        timeline_toolbar.setFloatable(False)
        timeline_toolbar.addWidget(self._timeline_widget)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, timeline_toolbar)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._build_menu()
        self._setup_shortcuts()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("File")
        open_action = file_menu.addAction("Open MCAP...", self._open_mcap)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        # Panels menu
        panel_menu = menu_bar.addMenu("Panels")
        for name in PanelRegistry.all_names():
            action = panel_menu.addAction(f"Add {name}")
            action.triggered.connect(
                lambda checked, n=name: self.dock_manager.add_panel(n)
            )

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._open_mcap)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(
            QKeySequence("Ctrl+P"), self, activated=self._show_quick_plot_dialog
        )
        QShortcut(QKeySequence("Space"), self, activated=self._toggle_playback)

    # -- File open -----------------------------------------------------------

    def _open_mcap(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open MCAP file", "", "MCAP Files (*.mcap);;All Files (*)"
        )
        if not path:
            return
        self._load_session(Path(path))

    def load_mcap(self, path: Path) -> None:
        """Programmatic entry point for loading an MCAP file."""
        self._load_session(path)

    def _load_session(self, path: Path) -> None:
        session = LogSession(path)
        self.ctx.sessions.append(session)

        self._status_bar.showMessage(f"Loading {path.name}...")

        # Wire up data store to variable browser
        self._var_browser.set_data_store(session.data_store)

        session.loading_finished.connect(self._on_session_loaded)
        session.error_occurred.connect(self._on_session_error)
        session.start()

    def _on_session_loaded(self) -> None:
        """Update timeline range from all sessions and show summary."""
        t_min, t_max = float("inf"), float("-inf")
        total_topics = 0
        total_messages = 0
        for session in self.ctx.sessions:
            ds = session.data_store
            r = ds.time_range
            if r[0] < t_min:
                t_min = r[0]
            if r[1] > t_max:
                t_max = r[1]
            total_topics += len(ds.topics)
            total_messages += sum(
                info.message_count for info in ds.topics.values()
            )
        if t_min < t_max:
            self.ctx.timeline.set_range(t_min, t_max)

        duration = t_max - t_min if t_max > t_min else 0
        summary_parts = [
            f"{total_topics} topics",
            f"{total_messages:,} messages",
            f"{duration:.1f}s duration",
        ]
        for session in reversed(self.ctx.sessions):
            if hasattr(session, "metrics") and session.metrics:
                mem = session.metrics.get("memory_current_mb", 0)
                load_t = session.metrics.get("load_time_s", 0)
                summary_parts.append(f"{mem:.0f} MB")
                summary_parts.append(f"loaded in {load_t:.2f}s")
                break

        self._status_bar.showMessage("Loaded: " + ", ".join(summary_parts))

    def _on_session_error(self, msg: str) -> None:
        self._status_bar.showMessage(f"Load error: {msg}")

    # -- Signal double-click → plot ------------------------------------------

    def _on_signal_double_clicked(self, full_path: str) -> None:
        """Add the signal to the focused chart, or create a new one."""
        from jig.panels.chart_panel import ChartPanel

        parts = full_path.rsplit("/", 1)
        if len(parts) != 2:
            return
        ref = SignalRef(topic=parts[0], field=parts[1])

        # Find the focused chart panel
        chart = self._find_focused_chart()
        if chart is None:
            # Create a new chart and add the signal
            chart = self.dock_manager.add_panel("Chart")

        if isinstance(chart, ChartPanel):
            chart.add_signal(ref)

    def _find_focused_chart(self):
        """Return the most recently focused ChartPanel, or None."""
        from jig.panels.chart_panel import ChartPanel

        # PyQtAds tracks the focused dock widget
        focused_dw = self.dock_manager.ads_dock_manager.focusedDockWidget()
        if focused_dw is not None:
            w = focused_dw.widget()
            if isinstance(w, ChartPanel):
                return w

        # Fallback: return the first open chart
        for panel in self.dock_manager.panels:
            if isinstance(panel, ChartPanel):
                return panel
        return None

    # -- Shortcuts -----------------------------------------------------------

    def _focus_search(self) -> None:
        self._var_browser.focus_search()

    def _toggle_playback(self) -> None:
        self.ctx.timeline.toggle_playing()

    def _show_quick_plot_dialog(self) -> None:
        from jig.shell.quick_plot_dialog import QuickPlotDialog

        ds = self.ctx.active_data_store
        if ds is None:
            return
        dlg = QuickPlotDialog(ds, parent=self)
        if dlg.exec():
            selected = dlg.selected_paths()
            for path in selected:
                self._on_signal_double_clicked(path)
