"""PanelBase — abstract base class for all Jig panels."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from jig.core.app_context import AppContext


class PanelToolbar(QWidget):
    """Slim toolbar at the top of every panel.

    Provides a standard layout:
      [type_icon] [title_label] [... custom controls ...] [stretch]
    Subclasses add their own controls via ``add_widget()`` / ``add_stretch()``.
    """

    def __init__(self, type_icon: str = "", title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(
            "PanelToolbar { background: #232327; border-bottom: 1px solid #333; }"
        )
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 0, 6, 0)
        self._layout.setSpacing(6)

        if type_icon:
            icon_label = QLabel(type_icon)
            icon_label.setStyleSheet("font-size: 13px;")
            self._layout.addWidget(icon_label)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("font-size: 11px; color: #aaa;")
        self._layout.addWidget(self._title_label)

        # Stretch goes at the end by default; custom controls insert before it
        self._layout.addStretch()

    @property
    def title(self) -> str:
        return self._title_label.text()

    @title.setter
    def title(self, text: str) -> None:
        self._title_label.setText(text)

    def add_widget(self, widget: QWidget) -> None:
        """Insert a widget before the trailing stretch."""
        self._layout.insertWidget(self._layout.count() - 1, widget)

    def add_separator(self) -> None:
        sep = QLabel("|")
        sep.setStyleSheet("color: #444; font-size: 11px;")
        self.add_widget(sep)


class PanelBase(QWidget):
    """Base class every panel must implement.

    Provides:
    - A shared ``PanelToolbar`` at the top (access via ``self.toolbar``)
    - Access to AppContext (timeline, sessions, data)
    - A per-panel render timer (~60 fps) for continuous updates
    - Connection to TimelineController.time_changed for immediate scrub response
    - State serialization for layout save/load
    """

    #: Human-readable name shown in menus. Override in subclass.
    panel_type_name: str = "Panel"
    #: Icon shown in the toolbar. Override in subclass.
    panel_icon: str = ""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        # Root layout — toolbar + content area
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

        # Panel toolbar (shared across all panel types)
        self.toolbar = PanelToolbar(
            type_icon=self.panel_icon,
            title=self.panel_type_name,
        )
        self._root_layout.addWidget(self.toolbar)

        # Content area — subclasses add their widgets here
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._root_layout.addWidget(self._content, stretch=1)

        # Per-panel render timer (~60 fps)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(16)  # ~60 fps
        self._render_timer.timeout.connect(self._on_render_tick)

        # Connect to timeline for immediate scrub response
        self.ctx.timeline.time_changed.connect(self.on_time_changed)

    def add_content_widget(self, widget: QWidget, stretch: int = 0) -> None:
        """Add a widget to the panel's content area (below the toolbar)."""
        self._content_layout.addWidget(widget, stretch=stretch)

    # -- Subclass interface --------------------------------------------------

    @abstractmethod
    def on_time_changed(self, t: float) -> None:
        """Called when the global timeline time changes (scrub or playback)."""
        ...

    def on_render_tick(self) -> None:
        """Called at ~60 fps when the render timer is running.

        Override for continuous rendering (e.g. 3D viewport animation).
        Default does nothing.
        """

    def get_state(self) -> dict[str, Any]:
        """Return panel state for serialization. Override to persist config."""
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore panel state from deserialized dict. Override to restore."""

    # -- Render timer control ------------------------------------------------

    def start_render_timer(self) -> None:
        self._render_timer.start()

    def stop_render_timer(self) -> None:
        self._render_timer.stop()

    def _on_render_tick(self) -> None:
        self.on_render_tick()
