"""PanelBase — abstract base class for all Jig panels."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from jig.core.app_context import AppContext


class PanelBase(QWidget):
    """Base class every panel must implement.

    Provides:
    - Access to AppContext (timeline, sessions, data)
    - A per-panel render timer (~60 fps) for continuous updates
    - Connection to TimelineController.time_changed for immediate scrub response
    - State serialization for layout save/load
    """

    #: Human-readable name shown in menus. Override in subclass.
    panel_type_name: str = "Panel"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx

        # Per-panel render timer (~60 fps)
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(16)  # ~60 fps
        self._render_timer.timeout.connect(self._on_render_tick)

        # Connect to timeline for immediate scrub response
        self.ctx.timeline.time_changed.connect(self.on_time_changed)

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
