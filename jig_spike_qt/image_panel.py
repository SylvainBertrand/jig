"""Image display panel synced to global timeline."""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jig_spike_qt.data_store import DataStore


class ImagePanel(QWidget):
    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self.data_store = data_store
        self.setMinimumSize(320, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel("No image")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #1a1a1a;")
        layout.addWidget(self.image_label, stretch=1)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("font-size: 11px; padding: 2px;")
        layout.addWidget(self.info_label)

        self.data_store.timeline_changed.connect(self._on_timeline)
        self._update_image()

    def _update_image(self):
        ts, img = self.data_store.get_image()
        if img is None:
            return

        h, w = img.shape[:2]
        ch = img.shape[2] if img.ndim == 3 else 1
        rgb = np.ascontiguousarray(img)

        if ch == 3:
            qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        else:
            qimg = QImage(rgb.data, w, h, w, QImage.Format.Format_Grayscale8)

        pixmap = QPixmap.fromImage(qimg.copy())
        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.info_label.setText(f"t = {ts:.3f} s  |  {w}\u00d7{h}")

    def _on_timeline(self, t: float):
        self._update_image()
