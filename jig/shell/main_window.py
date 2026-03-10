"""JigWindow — main application window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QToolBar,
    QWidget,
)

from jig.core.app_context import AppContext
from jig.core.timeline import TimelineController
from jig.panels.registry import PanelRegistry
from jig.sessions.log_session import LogSession
from jig.shell.dock_manager import DockManager
from jig.shell.timeline_widget import TimelineWidget
from jig.shell.topic_browser import TopicBrowser


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

        # Topic browser sidebar (standard QDockWidget, not managed by PyQtAds)
        self._topic_browser = TopicBrowser()
        sidebar_dock = QDockWidget("Topics", self)
        sidebar_dock.setWidget(self._topic_browser)
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

        self._build_menu()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction("Open MCAP...", self._open_mcap)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        # Panels menu
        panel_menu = menu_bar.addMenu("Panels")
        for name in PanelRegistry.all_names():
            action = panel_menu.addAction(f"Add {name}")
            action.triggered.connect(lambda checked, n=name: self.dock_manager.add_panel(n))

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

        # Wire up data store to topic browser
        self._topic_browser.set_data_store(session.data_store)

        # When loading finishes, update the timeline range
        session.loading_finished.connect(self._on_session_loaded)
        session.error_occurred.connect(lambda msg: print(f"Load error: {msg}"))
        session.start()

    def _on_session_loaded(self) -> None:
        """Update timeline range from all sessions."""
        t_min, t_max = float("inf"), float("-inf")
        for session in self.ctx.sessions:
            ds = session.data_store
            r = ds.time_range
            if r[0] < t_min:
                t_min = r[0]
            if r[1] > t_max:
                t_max = r[1]
        if t_min < t_max:
            self.ctx.timeline.set_range(t_min, t_max)
