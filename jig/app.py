"""JigApp — top-level application object."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jig.core.app_context import AppContext
from jig.core.timeline import TimelineController

# Import panels so their @PanelRegistry.register decorators run
import jig.panels.viewer_3d  # noqa: F401
import jig.panels.chart_panel  # noqa: F401
import jig.panels.image_panel  # noqa: F401

from jig.shell.main_window import JigWindow

_THEME_PATH = Path(__file__).parent / "resources" / "themes" / "dark.qss"


def _load_theme(app: QApplication) -> None:
    """Load the dark QSS theme."""
    if _THEME_PATH.exists():
        app.setStyleSheet(_THEME_PATH.read_text(encoding="utf-8"))


def _configure_pyqtgraph() -> None:
    """Set pyqtgraph global options to match the dark theme."""
    try:
        import pyqtgraph as pg

        pg.setConfigOptions(
            background="#1e1e1e",
            foreground="#cccccc",
            antialias=True,
            useOpenGL=False,
        )
    except ImportError:
        pass


class JigApp:
    """Owns the QApplication, AppContext, and main window."""

    def __init__(self, argv: list[str] | None = None) -> None:
        self._qapp = QApplication(argv or sys.argv)
        _load_theme(self._qapp)
        _configure_pyqtgraph()

        self._timeline = TimelineController()
        self._ctx = AppContext(timeline=self._timeline)
        self._window = JigWindow(self._ctx)

    @property
    def window(self) -> JigWindow:
        return self._window

    @property
    def ctx(self) -> AppContext:
        return self._ctx

    def run(self) -> int:
        """Show the main window and enter the Qt event loop."""
        self._window.show()
        return self._qapp.exec()

    def load_mcap(self, path: Path) -> None:
        """Convenience: load an MCAP file into a new LogSession."""
        self._window.load_mcap(path)

    def generate_and_load_test_data(self, fmt: str = "json") -> None:
        """Generate synthetic MCAP and load it (for development)."""
        from jig.io.mcap_generator import generate_mcap

        mcap_path = Path(tempfile.gettempdir()) / f"jig_test_{fmt}.mcap"
        generate_mcap(str(mcap_path), fmt=fmt)
        self.load_mcap(mcap_path)
