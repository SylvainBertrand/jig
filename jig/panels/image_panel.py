"""ImagePanel — displays image topic synced to the global timeline."""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QScrollArea,
    QWidget,
)

from jig.core.app_context import AppContext
from jig.panels.base import PanelBase
from jig.panels.registry import PanelRegistry

try:
    from PIL import Image as PILImage

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


@PanelRegistry.register
class ImagePanel(PanelBase):
    panel_type_name = "Image"
    panel_icon = "\U0001f5bc"  # 🖼

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.setMinimumSize(320, 260)
        self._topic: str = ""
        self._fit_to_panel: bool = True
        self._show_info: bool = True

        # -- Toolbar controls --
        topic_label = QLabel("Topic:")
        self.toolbar.add_widget(topic_label)

        self._topic_combo = QComboBox()
        self._topic_combo.setMinimumWidth(160)
        self._topic_combo.setToolTip("Image topic")
        self._topic_combo.currentTextChanged.connect(self._on_topic_selected)
        self.toolbar.add_widget(self._topic_combo)

        self.toolbar.add_separator()

        self._fit_cb = QCheckBox("Fit")
        self._fit_cb.setChecked(True)
        self._fit_cb.setToolTip("Fit image to panel size")
        self._fit_cb.toggled.connect(self._on_fit_toggled)
        self.toolbar.add_widget(self._fit_cb)

        self._info_cb = QCheckBox("Info")
        self._info_cb.setChecked(True)
        self._info_cb.setToolTip("Show image info overlay")
        self._info_cb.toggled.connect(self._on_info_toggled)
        self.toolbar.add_widget(self._info_cb)

        # -- Image display --
        self._image_label = QLabel("No image")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: #000000;")

        # Scroll area for original-size mode
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidget(self._image_label)
        self._scroll_area.setWidgetResizable(True)
        self.add_content_widget(self._scroll_area, stretch=1)

        # Info label at bottom
        self._info_label = QLabel("")
        self._info_label.setObjectName("panelStatus")
        self._info_label.setStyleSheet("font-size: 10px; color: #808080; padding: 2px 6px;")
        self.add_content_widget(self._info_label)

        # LRU cache for decoded images
        self._decode_cache = _ImageCache(maxsize=16)

        # Auto-select first image topic
        self._refresh_topics()
        for session in self.ctx.sessions:
            session.data_store.data_changed.connect(self._refresh_topics)

    # -- Topic selection -----------------------------------------------------

    def _refresh_topics(self) -> None:
        ds = self.ctx.active_data_store
        if ds is None:
            return
        topics = ds.message_topics()
        current = self._topic_combo.currentText()
        self._topic_combo.blockSignals(True)
        self._topic_combo.clear()
        self._topic_combo.addItems(topics)
        if current in topics:
            self._topic_combo.setCurrentText(current)
        elif topics:
            self._topic_combo.setCurrentIndex(0)
            self._topic = topics[0]
        self._topic_combo.blockSignals(False)
        self._update_image()

    def _on_topic_selected(self, topic: str) -> None:
        self._topic = topic
        self._update_image()

    # -- Config toggles ------------------------------------------------------

    def _on_fit_toggled(self, checked: bool) -> None:
        self._fit_to_panel = checked
        self._scroll_area.setWidgetResizable(checked)
        self._update_image()

    def _on_info_toggled(self, checked: bool) -> None:
        self._show_info = checked
        self._info_label.setVisible(checked)

    # -- Image display -------------------------------------------------------

    def _update_image(self) -> None:
        ds = self.ctx.active_data_store
        if ds is None or not self._topic:
            return
        result = ds.get_message_at(self._topic, self.ctx.timeline.current_time)
        if result is None:
            return

        ts, raw = result
        img = self._decode_image(raw)
        if img is None:
            return

        h, w = img.shape[:2]
        ch = img.shape[2] if img.ndim == 3 else 1
        rgb = np.ascontiguousarray(img)

        if ch >= 3:
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        else:
            qimg = QImage(rgb.data, w, h, w, QImage.Format.Format_Grayscale8)

        pixmap = QPixmap.fromImage(qimg.copy())

        if self._fit_to_panel:
            self._image_label.setPixmap(
                pixmap.scaled(
                    self._scroll_area.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self._image_label.setPixmap(pixmap)
            self._image_label.resize(pixmap.size())

        # Info text
        encoding = ""
        if isinstance(raw, dict):
            encoding = raw.get("format", raw.get("encoding", ""))
        info_parts = [f"t = {ts:.3f} s", f"{w}\u00d7{h}"]
        if encoding:
            info_parts.append(encoding)
        self._info_label.setText("  |  ".join(info_parts))
        self.toolbar.title = f"Image ({self._topic.rsplit('/', 1)[-1]})"

    def _decode_image(self, raw: Any) -> np.ndarray | None:
        if isinstance(raw, np.ndarray):
            return raw
        if isinstance(raw, dict) and "data" in raw:
            data = raw["data"]
            if isinstance(data, (list, tuple)):
                data = bytes(data)
            cache_key = id(data)
            cached = self._decode_cache.get(cache_key)
            if cached is not None:
                return cached
            img = _decode_compressed(data)
            if img is not None:
                self._decode_cache.put(cache_key, img)
            return img
        return None

    # -- PanelBase interface -------------------------------------------------

    def on_time_changed(self, t: float) -> None:
        self._update_image()

    def get_state(self) -> dict[str, Any]:
        return {
            "topic": self._topic,
            "fit_to_panel": self._fit_to_panel,
            "show_info": self._show_info,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self._fit_to_panel = state.get("fit_to_panel", True)
        self._fit_cb.setChecked(self._fit_to_panel)
        self._show_info = state.get("show_info", True)
        self._info_cb.setChecked(self._show_info)
        self._info_label.setVisible(self._show_info)

        topic = state.get("topic", "")
        if topic:
            self._topic = topic
            self._topic_combo.setCurrentText(topic)


# ---------------------------------------------------------------------------
# Image decoding + cache
# ---------------------------------------------------------------------------

def _decode_compressed(data: bytes) -> np.ndarray | None:
    if not _HAS_PIL:
        return None
    try:
        pil_img = PILImage.open(io.BytesIO(data))
        pil_img = pil_img.convert("RGB")
        return np.array(pil_img)
    except Exception:
        return None


class _ImageCache:
    def __init__(self, maxsize: int = 16) -> None:
        self._maxsize = maxsize
        self._cache: dict[int, np.ndarray] = {}
        self._order: list[int] = []

    def get(self, key: int) -> np.ndarray | None:
        if key in self._cache:
            self._order.remove(key)
            self._order.append(key)
            return self._cache[key]
        return None

    def put(self, key: int, value: np.ndarray) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self._maxsize:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = value
        self._order.append(key)
