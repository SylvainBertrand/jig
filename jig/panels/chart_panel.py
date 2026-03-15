"""ChartPanel — time-series chart using pyqtgraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QColorDialog,
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

DEFAULT_COLORS = [
    "#e6194b", "#3cb44b", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45",
    "#fabebe", "#008080", "#e6beff", "#9a6324",
]

LINE_STYLES = {
    "solid": Qt.PenStyle.SolidLine,
    "dashed": Qt.PenStyle.DashLine,
    "dotted": Qt.PenStyle.DotLine,
}

LINE_WIDTHS = [1, 2, 3]

_BTN_STYLE = (
    "QPushButton { font-size: 11px; padding: 2px 6px; border: 1px solid #555; "
    "border-radius: 3px; background: #2a2a2e; color: #ddd; }"
    "QPushButton:hover { background: #3a3a3e; }"
)


@dataclass
class _SignalConfig:
    """Per-signal visual configuration."""

    ref: SignalRef
    color: str = "#e6194b"
    width: int = 1
    style: str = "solid"
    visible: bool = True


class _SignalChip(QWidget):
    """Small colored tag representing a plotted signal, with a close button."""

    def __init__(
        self, config: _SignalConfig, on_remove, on_right_click,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._on_right_click = on_right_click

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 2, 1)
        layout.setSpacing(2)

        self._dot = QLabel("\u25cf")
        self._dot.setStyleSheet(f"color: {config.color}; font-size: 10px;")
        layout.addWidget(self._dot)

        label = QLabel(config.ref.field)
        label.setStyleSheet("font-size: 11px;")
        label.setToolTip(config.ref.full_path)
        layout.addWidget(label)

        close_btn = QPushButton("\u00d7")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 12px; color: #888; }"
            "QPushButton:hover { color: #e00; }"
        )
        close_btn.setToolTip("Remove signal")
        close_btn.clicked.connect(lambda: on_remove(config.ref))
        layout.addWidget(close_btn)

        opacity = "" if config.visible else " opacity: 0.4;"
        self.setStyleSheet(
            f"background: #2a2a2e; border-radius: 3px; margin: 1px;{opacity}"
        )

    def contextMenuEvent(self, event) -> None:
        self._on_right_click(self.config, event.globalPos())


@PanelRegistry.register
class ChartPanel(PanelBase):
    panel_type_name = "Chart"
    panel_icon = "\U0001f4ca"  # 📊

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.setMinimumSize(400, 250)
        self._configs: list[_SignalConfig] = []
        self._plot_items: list = []
        self._drop_highlight = False
        self._follow_playback = True

        # -- Toolbar controls --
        auto_y_btn = QPushButton("Auto Y")
        auto_y_btn.setStyleSheet(_BTN_STYLE)
        auto_y_btn.setToolTip("Auto-scale Y axis")
        auto_y_btn.clicked.connect(self._auto_scale_y)
        self.toolbar.add_widget(auto_y_btn)

        reset_btn = QPushButton("Reset Zoom")
        reset_btn.setStyleSheet(_BTN_STYLE)
        reset_btn.clicked.connect(self._reset_zoom)
        self.toolbar.add_widget(reset_btn)

        # -- Signal chips header --
        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(4, 2, 4, 2)
        self._chips_layout.setSpacing(2)
        self._chips_layout.addStretch()
        self.add_content_widget(self._chips_widget)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px; padding: 2px;")

        if not HAS_PYQTGRAPH:
            self.add_content_widget(QLabel("pyqtgraph not installed"))
            self.add_content_widget(self._status_label)
            return

        pg.setConfigOptions(antialias=False, useOpenGL=False)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setLabel("bottom", "Time", units="s")
        self._plot_widget.setLabel("left", "Value")
        self._plot_widget.addLegend(offset=(10, 10))
        self.add_content_widget(self._plot_widget, stretch=1)
        self.add_content_widget(self._status_label)

        # Time cursor
        self._cursor = pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen("w", width=2, style=pg.QtCore.Qt.PenStyle.DashLine),
        )
        self._plot_widget.addItem(self._cursor)

        # Crosshair
        self._vline = pg.InfiniteLine(angle=90, pen=pg.mkPen("#555", width=1))
        self._hline = pg.InfiniteLine(angle=0, pen=pg.mkPen("#555", width=1))
        self._plot_widget.addItem(self._vline, ignoreBounds=True)
        self._plot_widget.addItem(self._hline, ignoreBounds=True)
        self._vline.setVisible(False)
        self._hline.setVisible(False)

        self._proxy = pg.SignalProxy(
            self._plot_widget.scene().sigMouseMoved,
            rateLimit=60, slot=self._on_mouse_moved,
        )

        # Context menu
        self._plot_widget.plotItem.setMenuEnabled(False)
        self._plot_widget.setContextMenuPolicy(
            pg.QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._plot_widget.customContextMenuRequested.connect(self._show_context_menu)

        # Accept drops
        self.setAcceptDrops(True)

        # Auto-populate
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
        if not self._configs:
            self._auto_populate()

    def add_signal(self, ref: SignalRef, color: str | None = None,
                   width: int = 1, style: str = "solid") -> None:
        if not HAS_PYQTGRAPH:
            return
        if any(c.ref == ref for c in self._configs):
            return
        ds = self.ctx.active_data_store
        if ds is None:
            return
        series = ds.get_series(ref.full_path)
        if series is None:
            return

        if color is None:
            color = DEFAULT_COLORS[len(self._configs) % len(DEFAULT_COLORS)]

        config = _SignalConfig(ref=ref, color=color, width=width, style=style)
        pen = pg.mkPen(color, width=width, style=LINE_STYLES.get(style, Qt.PenStyle.SolidLine))
        item = self._plot_widget.plot(
            series.timestamps, series.values, pen=pen, name=ref.field,
        )
        self._configs.append(config)
        self._plot_items.append(item)
        self._rebuild_chips()

    def remove_signal(self, ref: SignalRef) -> None:
        if not HAS_PYQTGRAPH:
            return
        idx = next((i for i, c in enumerate(self._configs) if c.ref == ref), None)
        if idx is None:
            return
        self._plot_widget.removeItem(self._plot_items[idx])
        del self._configs[idx]
        del self._plot_items[idx]
        self._rebuild_chips()
        self._rebuild_legend()

    def remove_all_signals(self) -> None:
        for item in self._plot_items:
            self._plot_widget.removeItem(item)
        self._configs.clear()
        self._plot_items.clear()
        self._rebuild_chips()
        self._plot_widget.plotItem.legend.clear()

    def _rebuild_legend(self) -> None:
        self._plot_widget.plotItem.legend.clear()
        for cfg, item in zip(self._configs, self._plot_items):
            if cfg.visible:
                self._plot_widget.plotItem.legend.addItem(item, cfg.ref.field)

    def _rebuild_chips(self) -> None:
        while self._chips_layout.count() > 1:
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for cfg in self._configs:
            chip = _SignalChip(cfg, self.remove_signal, self._show_signal_menu)
            self._chips_layout.insertWidget(
                self._chips_layout.count() - 1, chip
            )

    def _update_signal_pen(self, cfg: _SignalConfig) -> None:
        """Update the pen of a plotted signal after config change."""
        idx = next((i for i, c in enumerate(self._configs) if c.ref == cfg.ref), None)
        if idx is None:
            return
        item = self._plot_items[idx]
        pen = pg.mkPen(
            cfg.color, width=cfg.width,
            style=LINE_STYLES.get(cfg.style, Qt.PenStyle.SolidLine),
        )
        item.setPen(pen)
        item.setVisible(cfg.visible)
        self._rebuild_chips()
        self._rebuild_legend()

    # -- Signal right-click menu ---------------------------------------------

    def _show_signal_menu(self, cfg: _SignalConfig, pos) -> None:
        menu = QMenu(self)

        # Color
        menu.addAction("Change Color...", lambda: self._change_signal_color(cfg))

        # Width submenu
        width_menu = menu.addMenu("Line Width")
        for w in LINE_WIDTHS:
            action = width_menu.addAction(f"{w}px")
            action.setCheckable(True)
            action.setChecked(cfg.width == w)
            action.triggered.connect(lambda checked, w=w: self._set_signal_width(cfg, w))

        # Style submenu
        style_menu = menu.addMenu("Line Style")
        for name in LINE_STYLES:
            action = style_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(cfg.style == name)
            action.triggered.connect(lambda checked, s=name: self._set_signal_style(cfg, s))

        # Visibility
        vis_action = menu.addAction("Visible")
        vis_action.setCheckable(True)
        vis_action.setChecked(cfg.visible)
        vis_action.toggled.connect(lambda v: self._set_signal_visible(cfg, v))

        menu.addSeparator()
        menu.addAction("Remove", lambda: self.remove_signal(cfg.ref))

        menu.exec(pos)

    def _change_signal_color(self, cfg: _SignalConfig) -> None:
        color = QColorDialog.getColor(QColor(cfg.color), self, "Signal Color")
        if color.isValid():
            cfg.color = color.name()
            self._update_signal_pen(cfg)

    def _set_signal_width(self, cfg: _SignalConfig, width: int) -> None:
        cfg.width = width
        self._update_signal_pen(cfg)

    def _set_signal_style(self, cfg: _SignalConfig, style: str) -> None:
        cfg.style = style
        self._update_signal_pen(cfg)

    def _set_signal_visible(self, cfg: _SignalConfig, visible: bool) -> None:
        cfg.visible = visible
        self._update_signal_pen(cfg)

    # -- Context menu --------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)

        add_menu = menu.addMenu("Add Signal...")
        ds = self.ctx.active_data_store
        if ds is not None:
            existing = {c.ref for c in self._configs}
            for name in ds.series_names:
                parts = name.rsplit("/", 1)
                if len(parts) == 2:
                    ref = SignalRef(topic=parts[0], field=parts[1])
                    if ref not in existing:
                        action = add_menu.addAction(name)
                        action.triggered.connect(
                            lambda checked, r=ref: self.add_signal(r)
                        )

        menu.addAction("Quick Plot... (Ctrl+P)", self._open_quick_plot)
        menu.addSeparator()
        menu.addAction("Remove All Signals", self.remove_all_signals)
        menu.addSeparator()
        menu.addAction("Auto-scale Y Axis", self._auto_scale_y)
        menu.addAction("Reset Zoom", self._reset_zoom)

        menu.addSeparator()
        follow_action = menu.addAction("Follow playback cursor")
        follow_action.setCheckable(True)
        follow_action.setChecked(self._follow_playback)
        follow_action.toggled.connect(self._set_follow_playback)

        menu.exec(self._plot_widget.mapToGlobal(pos))

    def _auto_scale_y(self) -> None:
        if HAS_PYQTGRAPH:
            self._plot_widget.enableAutoRange(axis="y")

    def _reset_zoom(self) -> None:
        if HAS_PYQTGRAPH:
            self._plot_widget.enableAutoRange()

    def _set_follow_playback(self, follow: bool) -> None:
        self._follow_playback = follow

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

        ds = self.ctx.active_data_store
        if ds is None:
            return
        parts = [f"t={x:.3f}s"]
        for cfg in self._configs:
            if cfg.visible:
                val = ds.get_scalar_at(cfg.ref.full_path, x)
                parts.append(f"{cfg.ref.field}={val:.4f}")
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
        self._cursor.setValue(t)

        if self._follow_playback and self.ctx.timeline.playing:
            vb = self._plot_widget.plotItem.vb
            x_range = vb.viewRange()[0]
            view_width = x_range[1] - x_range[0]
            threshold = x_range[0] + view_width * 0.8
            if t > threshold:
                new_start = t - view_width * 0.2
                vb.setXRange(new_start, new_start + view_width, padding=0)

    def get_state(self) -> dict[str, Any]:
        return {
            "signals": [
                {
                    "topic": c.ref.topic,
                    "field": c.ref.field,
                    "color": c.color,
                    "width": c.width,
                    "style": c.style,
                    "visible": c.visible,
                }
                for c in self._configs
            ],
            "follow_playback": self._follow_playback,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._follow_playback = state.get("follow_playback", True)
        for s in state.get("signals", []):
            self.add_signal(
                SignalRef(topic=s["topic"], field=s["field"]),
                color=s.get("color"),
                width=s.get("width", 1),
                style=s.get("style", "solid"),
            )
            # Restore visibility
            if not s.get("visible", True):
                cfg = self._configs[-1] if self._configs else None
                if cfg:
                    cfg.visible = False
                    self._update_signal_pen(cfg)
