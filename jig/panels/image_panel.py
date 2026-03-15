"""ImagePanel — displays image topic synced to the global timeline."""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

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

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.setMinimumSize(320, 260)
        self._topic: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Topic selector dropdown
        self._topic_combo = QComboBox()
        self._topic_combo.currentTextChanged.connect(self._on_topic_selected)
        layout.addWidget(self._topic_combo)

        self._image_label = QLabel("No image")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: #1a1a1a;")
        layout.addWidget(self._image_label, stretch=1)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("font-size: 11px; padding: 2px;")
        layout.addWidget(self._info_label)

        # LRU cache for decoded images
        self._decode_cache = _ImageCache(maxsize=16)

        # Auto-select first image topic if data is loaded
        self._refresh_topics()

        # Listen for new data
        for session in self.ctx.sessions:
            session.data_store.data_changed.connect(self._refresh_topics)

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
        self._image_label.setPixmap(
            pixmap.scaled(
                self._image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        encoding = ""
        if isinstance(raw, dict):
            encoding = f"  |  {raw.get('format', raw.get('encoding', ''))}"
        self._info_label.setText(f"t = {ts:.3f} s  |  {w}\u00d7{h}{encoding}")

    def _decode_image(self, raw: Any) -> np.ndarray | None:
        """Decode raw image data to numpy array (with caching)."""
        # Already a numpy array (JSON generator path)
        if isinstance(raw, np.ndarray):
            return raw

        # CompressedImage dict: {"format": "jpeg", "data": b"..."}
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
        return {"topic": self._topic}

    def set_state(self, state: dict[str, Any]) -> None:
        topic = state.get("topic", "")
        if topic:
            self._topic = topic
            self._topic_combo.setCurrentText(topic)


# ---------------------------------------------------------------------------
# Image decoding + cache
# ---------------------------------------------------------------------------

def _decode_compressed(data: bytes) -> np.ndarray | None:
    """Decode JPEG/PNG bytes to numpy RGB array."""
    if not _HAS_PIL:
        return None
    try:
        pil_img = PILImage.open(io.BytesIO(data))
        pil_img = pil_img.convert("RGB")
        return np.array(pil_img)
    except Exception:
        return None


class _ImageCache:
    """Simple LRU cache for decoded images keyed by object id."""

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
