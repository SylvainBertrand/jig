"""MCAP reader — loads an MCAP file into a DataStore."""

from __future__ import annotations

import io
import json
import time
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image as PILImage

from mcap.reader import make_reader

from jig.core.data_store import DataStore
from jig.core.types import TopicInfo


def load_mcap_into(data_store: DataStore, path: str | Path) -> dict[str, Any]:
    """Load an MCAP file into *data_store*. Returns performance metrics.

    This function is designed to be called from a background thread via
    ``BackgroundExecutor.submit()``.

    For ``sensor_msgs/JointState``-style messages (JSON with "name" and
    "position" arrays), each joint is extracted as a separate scalar series
    (e.g. ``/joint_states/position[0]``).

    For image topics (raw JPEG/PNG bytes), images are stored as non-scalar
    messages indexed by timestamp.
    """
    path = str(path)
    tracemalloc.start()
    t0 = time.perf_counter()

    # Accumulate per-topic data before bulk-inserting
    joint_data: dict[str, dict[str, list]] = {}  # topic -> {"ts": [], "positions": [], "names": []}
    image_data: dict[str, list[tuple[float, np.ndarray]]] = {}  # topic -> [(t, img)]

    with open(path, "rb") as f:
        reader = make_reader(f)
        for schema, channel, message in reader.iter_messages():
            t = message.log_time / 1e9

            if channel.message_encoding == "json":
                msg = json.loads(message.data)
                if "position" in msg and "name" in msg:
                    _accumulate_joint_state(joint_data, channel.topic, t, msg)
                else:
                    # Generic JSON topic — store as non-scalar message
                    data_store.add_message(channel.topic, t, msg)

            elif channel.message_encoding == "raw":
                try:
                    pil_img = PILImage.open(io.BytesIO(message.data))
                    img_array = np.array(pil_img)
                    if channel.topic not in image_data:
                        image_data[channel.topic] = []
                    image_data[channel.topic].append((t, img_array))
                except Exception:
                    data_store.add_message(channel.topic, t, message.data)

    # Bulk-insert joint scalar series
    for topic, jd in joint_data.items():
        ts_array = np.array(jd["ts"])
        names = jd["names"]
        positions = np.array(jd["positions"])  # (N, num_joints)

        fields = []
        for j, name in enumerate(names):
            field_name = f"position[{j}]"
            full_path = f"{topic}/{field_name}"
            data_store.add_series(full_path, ts_array, positions[:, j])
            fields.append(field_name)

        data_store.add_topic(TopicInfo(
            name=topic,
            message_type="JointState",
            message_count=len(ts_array),
            fields=fields,
        ))

    # Bulk-insert image topics
    for topic, frames in image_data.items():
        for t, img in frames:
            data_store.add_message(topic, t, img)

        data_store.add_topic(TopicInfo(
            name=topic,
            message_type="CompressedImage",
            message_count=len(frames),
        ))

    data_store.data_changed.emit()

    load_time = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "load_time_s": load_time,
        "memory_current_mb": current / 1e6,
        "memory_peak_mb": peak / 1e6,
        "path": path,
    }


def _accumulate_joint_state(
    joint_data: dict, topic: str, t: float, msg: dict
) -> None:
    if topic not in joint_data:
        joint_data[topic] = {"ts": [], "positions": [], "names": msg["name"]}
    joint_data[topic]["ts"].append(t)
    joint_data[topic]["positions"].append(msg["position"])
