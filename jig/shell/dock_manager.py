"""DockManager — creates and tracks docked panels."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QMainWindow

from jig.core.app_context import AppContext
from jig.panels.base import PanelBase
from jig.panels.registry import PanelRegistry


class DockManager:
    """Manages the lifecycle of docked panels in a QMainWindow."""

    def __init__(self, window: QMainWindow, ctx: AppContext) -> None:
        self._window = window
        self._ctx = ctx
        self._docks: list[QDockWidget] = []
        self._panel_count = 0

    def add_panel(self, panel_type_name: str) -> PanelBase | None:
        """Instantiate and dock a panel by its registered type name."""
        panel_cls = PanelRegistry.get(panel_type_name)
        if panel_cls is None:
            return None

        self._panel_count += 1
        label = f"{panel_type_name} #{self._panel_count}"

        panel = panel_cls(self._ctx)
        dock = QDockWidget(label, self._window)
        dock.setWidget(panel)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self._docks.append(dock)
        return panel

    @property
    def panels(self) -> list[PanelBase]:
        """Return all live panels (skipping closed/destroyed docks)."""
        result = []
        for dock in self._docks:
            w = dock.widget()
            if isinstance(w, PanelBase):
                result.append(w)
        return result

    def get_layout_state(self) -> list[dict[str, Any]]:
        """Serialize open panels and their state."""
        states = []
        for dock in self._docks:
            w = dock.widget()
            if isinstance(w, PanelBase):
                states.append({
                    "type": w.panel_type_name,
                    "title": dock.windowTitle(),
                    "floating": dock.isFloating(),
                    "state": w.get_state(),
                })
        return states

    def restore_layout_state(self, states: list[dict[str, Any]]) -> None:
        """Recreate panels from serialized state."""
        for s in states:
            panel = self.add_panel(s["type"])
            if panel is not None:
                panel.set_state(s.get("state", {}))
