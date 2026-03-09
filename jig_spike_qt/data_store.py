"""In-memory data store loaded from MCAP, with timeline state."""

import io
import json

import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import QObject, Signal

from mcap.reader import make_reader


class DataStore(QObject):
    timeline_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.joint_timestamps: np.ndarray = np.array([])
        self.joint_positions: np.ndarray = np.empty((0, 7))
        self.image_timestamps: np.ndarray = np.array([])
        self.images: list[np.ndarray] = []
        self.t_min = 0.0
        self.t_max = 10.0
        self._current_time = 0.0

    @property
    def current_time(self) -> float:
        return self._current_time

    def set_time(self, t: float):
        self._current_time = float(np.clip(t, self.t_min, self.t_max))
        self.timeline_changed.emit(self._current_time)

    def load_mcap(self, path: str):
        joint_ts: list[float] = []
        joint_pos: list[list[float]] = []
        image_ts: list[float] = []
        images: list[np.ndarray] = []

        with open(path, "rb") as f:
            reader = make_reader(f)
            for schema, channel, message in reader.iter_messages():
                t = message.log_time / 1e9
                if channel.topic == "/joint_states":
                    msg = json.loads(message.data)
                    joint_ts.append(t)
                    joint_pos.append(msg["position"])
                elif channel.topic == "/camera/image_raw":
                    pil_img = PILImage.open(io.BytesIO(message.data))
                    image_ts.append(t)
                    images.append(np.array(pil_img))

        self.joint_timestamps = np.array(joint_ts)
        self.joint_positions = np.array(joint_pos) if joint_pos else np.empty((0, 7))
        self.image_timestamps = np.array(image_ts)
        self.images = images

        if len(joint_ts) > 0:
            all_ts = np.concatenate([self.joint_timestamps, self.image_timestamps])
            self.t_min = float(all_ts.min())
            self.t_max = float(all_ts.max())

    def get_joint_positions(self, t: float | None = None) -> np.ndarray:
        if t is None:
            t = self._current_time
        if len(self.joint_timestamps) == 0:
            return np.zeros(7)
        idx = int(np.searchsorted(self.joint_timestamps, t, side="right")) - 1
        idx = max(0, min(idx, len(self.joint_timestamps) - 1))
        return self.joint_positions[idx]

    def get_image(self, t: float | None = None) -> tuple[float, np.ndarray | None]:
        if t is None:
            t = self._current_time
        if len(self.image_timestamps) == 0:
            return 0.0, None
        idx = int(np.searchsorted(self.image_timestamps, t, side="right")) - 1
        idx = max(0, min(idx, len(self.image_timestamps) - 1))
        return float(self.image_timestamps[idx]), self.images[idx]
