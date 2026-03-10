"""DockManager — creates and tracks docked panels using Qt Advanced Docking System."""

from __future__ import annotations

import base64
from enum import Enum
from typing import Any

import PySide6QtAds as ads
from PySide6.QtWidgets import QMainWindow, QWidget

from jig.core.app_context import AppContext
from jig.panels.base import PanelBase
from jig.panels.registry import PanelRegistry


class DockArea(Enum):
    """Logical dock placement areas."""

    LEFT = ads.LeftDockWidgetArea
    RIGHT = ads.RightDockWidgetArea
    TOP = ads.TopDockWidgetArea
    BOTTOM = ads.BottomDockWidgetArea
    CENTER = ads.CenterDockWidgetArea


class DockManager:
    """Manages the lifecycle of docked panels via PyQtAds (CDockManager)."""

    def __init__(self, window: QMainWindow, ctx: AppContext) -> None:
        self._window = window
        self._ctx = ctx
        self._panel_count = 0

        # Configure CDockManager before it's shown
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.OpaqueSplitterResize, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.DockAreaHasCloseButton, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.DockAreaHasUndockButton, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.DockAreaHasTabsMenuButton, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.AllTabsHaveCloseButton, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.EqualSplitOnInsertion, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.FloatingContainerHasWidgetTitle, True
        )
        ads.CDockManager.setConfigFlag(
            ads.CDockManager.eConfigFlag.DockAreaDynamicTabsMenuButtonVisibility, True
        )

        self._dock_manager = ads.CDockManager(window)
        # Track dock widgets for iteration
        self._dock_widgets: list[ads.CDockWidget] = []

    @property
    def ads_dock_manager(self) -> ads.CDockManager:
        """Expose the underlying CDockManager (used by MainWindow for layout)."""
        return self._dock_manager

    def add_panel(
        self,
        panel_type_name: str,
        area: DockArea = DockArea.CENTER,
    ) -> PanelBase | None:
        """Instantiate and dock a panel by its registered type name."""
        panel_cls = PanelRegistry.get(panel_type_name)
        if panel_cls is None:
            return None

        self._panel_count += 1
        label = f"{panel_type_name} #{self._panel_count}"

        panel = panel_cls(self._ctx)

        dock_widget = self._dock_manager.createDockWidget(label)
        dock_widget.setWidget(panel)
        dock_widget.setFeatures(
            ads.CDockWidget.DockWidgetFeature.DockWidgetClosable
            | ads.CDockWidget.DockWidgetFeature.DockWidgetMovable
            | ads.CDockWidget.DockWidgetFeature.DockWidgetFloatable
            | ads.CDockWidget.DockWidgetFeature.DockWidgetFocusable
        )

        self._dock_manager.addDockWidget(area.value, dock_widget)
        self._dock_widgets.append(dock_widget)

        # Clean up panel when dock is closed
        dock_widget.closed.connect(lambda: self._on_dock_closed(dock_widget, panel))

        return panel

    def remove_panel(self, panel: PanelBase) -> None:
        """Remove and clean up a panel."""
        for dw in self._dock_widgets:
            if dw.widget() is panel:
                dw.closeDockWidget()
                break

    @property
    def panels(self) -> list[PanelBase]:
        """Return all live panels (skipping closed/destroyed docks)."""
        result = []
        for dw in self._dock_widgets:
            w = dw.widget()
            if isinstance(w, PanelBase) and not dw.isClosed():
                result.append(w)
        return result

    def get_all_panels(self) -> list[PanelBase]:
        """Return all live panels."""
        return self.panels

    def save_state(self) -> dict[str, Any]:
        """Serialize the full dock layout + panel states to a JSON-safe dict."""
        # Save PyQtAds geometry/layout as base64-encoded QByteArray
        raw_state = self._dock_manager.saveState()
        dock_state_b64 = base64.b64encode(bytes(raw_state)).decode("ascii")

        # Save per-panel info
        panel_states = []
        for dw in self._dock_widgets:
            w = dw.widget()
            if isinstance(w, PanelBase) and not dw.isClosed():
                panel_states.append(
                    {
                        "type": w.panel_type_name,
                        "title": dw.windowTitle(),
                        "object_name": dw.objectName(),
                        "floating": dw.isFloating(),
                        "state": w.get_state(),
                    }
                )

        return {
            "dock_state": dock_state_b64,
            "panels": panel_states,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Recreate panels and restore dock layout from a saved state dict."""
        panel_states = state.get("panels", [])
        dock_state_b64 = state.get("dock_state")

        # First, recreate all panels so the CDockManager knows about them
        for ps in panel_states:
            panel = self.add_panel(ps["type"])
            if panel is not None:
                panel.set_state(ps.get("state", {}))

        # Then restore the dock geometry/layout
        if dock_state_b64:
            raw = base64.b64decode(dock_state_b64)
            from PySide6.QtCore import QByteArray

            self._dock_manager.restoreState(QByteArray(raw))

    # Legacy compatibility with existing layout.py integration
    def get_layout_state(self) -> list[dict[str, Any]]:
        """Serialize open panels and their state (legacy format)."""
        return self.save_state().get("panels", [])

    def restore_layout_state(self, states: list[dict[str, Any]]) -> None:
        """Recreate panels from serialized state (legacy format)."""
        for s in states:
            panel = self.add_panel(s["type"])
            if panel is not None:
                panel.set_state(s.get("state", {}))

    def _on_dock_closed(self, dock_widget: ads.CDockWidget, panel: PanelBase) -> None:
        """Clean up when a dock widget is closed."""
        panel.stop_render_timer()
