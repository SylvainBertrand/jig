"""MCAP reader — loads an MCAP file into a DataStore.

Supports two message encodings:
- **CDR** (ROS 2 native): deserialized via ``mcap-ros2-support``.
- **JSON**: the lightweight format used by Jig's test-data generator.

For CDR messages the reader uses the channel schema to determine the ROS 2
message type and applies specialised extractors for common types
(``JointState``, ``CompressedImage``, ``PoseStamped``, …).  Any type that
does not have a specialised extractor is handled by a *generic* walker that
recursively pulls out every numeric leaf field as a scalar series.
"""

from __future__ import annotations

import io
import json
import time
import tracemalloc
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
from PIL import Image as PILImage

from mcap.reader import make_reader

from jig.core.data_store import DataStore
from jig.core.types import TopicInfo

# Optional CDR decoder — only available when mcap-ros2-support is installed.
try:
    from mcap_ros2.decoder import DecoderFactory as _Ros2DecoderFactory

    _HAS_ROS2 = True
except ImportError:
    _HAS_ROS2 = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_mcap_into(data_store: DataStore, path: str | Path) -> dict[str, Any]:
    """Load an MCAP file into *data_store*.  Returns performance metrics.

    Designed to be called from a background thread via
    ``BackgroundExecutor.submit()``.
    """
    path = str(path)
    tracemalloc.start()
    t0 = time.perf_counter()

    decoder_factories = []
    if _HAS_ROS2:
        decoder_factories.append(_Ros2DecoderFactory())

    # Accumulators — collect per-topic before bulk insert
    scalar_acc: dict[str, _ScalarAccumulator] = {}  # full_path -> acc
    msg_acc: dict[str, list[tuple[float, Any]]] = defaultdict(list)
    topic_meta: dict[str, _TopicMeta] = {}  # topic -> meta

    try:
        with open(path, "rb") as f:
            reader = make_reader(f, decoder_factories=decoder_factories)
            _read_messages(reader, decoder_factories, scalar_acc, msg_acc, topic_meta)
    except Exception as exc:
        # Corrupted / truncated / empty MCAP files: log and continue
        # with whatever data we managed to read
        print(f"MCAP read warning: {exc}")

    # Bulk-insert scalar series
    for full_path, acc in scalar_acc.items():
        ts = np.array(acc.timestamps, dtype=np.float64)
        vals = np.array(acc.values, dtype=np.float64)
        data_store.add_series(full_path, ts, vals)

    # Bulk-insert non-scalar messages
    for topic, msgs in msg_acc.items():
        for t, msg in msgs:
            data_store.add_message(topic, t, msg)

    # Register topics
    for topic, meta in topic_meta.items():
        # Collect fields from scalar_acc
        prefix = topic + "/"
        fields = sorted(
            full_path[len(prefix):]
            for full_path in scalar_acc
            if full_path.startswith(prefix)
        )
        data_store.add_topic(TopicInfo(
            name=topic,
            message_type=meta.message_type,
            message_count=meta.count,
            fields=fields,
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
        "topic_count": len(topic_meta),
        "message_count": sum(m.count for m in topic_meta.values()),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _ScalarAccumulator:
    __slots__ = ("timestamps", "values")

    def __init__(self) -> None:
        self.timestamps: list[float] = []
        self.values: list[float] = []

    def append(self, t: float, v: float) -> None:
        self.timestamps.append(t)
        self.values.append(v)


class _TopicMeta:
    __slots__ = ("message_type", "count")

    def __init__(self, message_type: str) -> None:
        self.message_type = message_type
        self.count = 0


# ---------------------------------------------------------------------------
# CDR / decoded message path
# ---------------------------------------------------------------------------

def _read_messages(reader, decoder_factories, scalar_acc, msg_acc, topic_meta) -> None:
    """Read all messages, using CDR decoders when available, raw fallback otherwise."""
    # Build a set of decodable encodings from the factories
    decoders: dict[tuple[str, int | None], Any] = {}

    for schema, channel, message in reader.iter_messages():
        t = message.log_time / 1e9
        topic = channel.topic
        msg_type = schema.name if schema else channel.message_encoding

        if topic not in topic_meta:
            topic_meta[topic] = _TopicMeta(msg_type)
        topic_meta[topic].count += 1

        # Try to decode with CDR decoder
        key = (channel.message_encoding, schema.id if schema else None)
        if key not in decoders:
            decoder = None
            for factory in decoder_factories:
                decoder = factory.decoder_for(channel.message_encoding, schema)
                if decoder is not None:
                    break
            decoders[key] = decoder

        decoder = decoders[key]
        if decoder is not None:
            try:
                decoded = decoder(message.data)
                extractor = _get_extractor(msg_type)
                extractor(topic, t, decoded, scalar_acc, msg_acc)
                continue
            except Exception:
                pass  # Fall through to raw handling

        # Raw / JSON fallback
        _handle_raw_message_data(
            channel, message, schema, t, topic, scalar_acc, msg_acc
        )


def _handle_raw_message_data(channel, message, schema, t, topic,
                             scalar_acc, msg_acc) -> None:
    """Handle a single un-decoded message (JSON or raw bytes)."""
    if channel.message_encoding == "json":
        try:
            msg = json.loads(message.data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        # JointState-like JSON (our test generator format)
        if isinstance(msg, dict) and "position" in msg and "name" in msg:
            _extract_json_joint_state(topic, t, msg, scalar_acc)
        else:
            _extract_generic_dict(topic, t, msg, scalar_acc, msg_acc)
    else:
        # Try as image
        try:
            pil_img = PILImage.open(io.BytesIO(message.data))
            img_array = np.array(pil_img)
            msg_acc[topic].append((t, img_array))
        except Exception:
            msg_acc[topic].append((t, message.data))


# ---------------------------------------------------------------------------
# Specialised extractors for common ROS 2 message types
# ---------------------------------------------------------------------------

_ExtractorFn = Callable[
    [str, float, Any, dict[str, _ScalarAccumulator], dict],
    None,
]


def _extract_joint_state(topic, t, msg, scalar_acc, msg_acc) -> None:
    """sensor_msgs/msg/JointState → per-joint scalar series."""
    names = getattr(msg, "name", [])
    positions = getattr(msg, "position", [])
    velocities = getattr(msg, "velocity", [])
    efforts = getattr(msg, "effort", [])

    for i, name in enumerate(names):
        if i < len(positions):
            _acc_scalar(scalar_acc, f"{topic}/position[{i}]", t, positions[i])
        if i < len(velocities) and velocities:
            _acc_scalar(scalar_acc, f"{topic}/velocity[{i}]", t, velocities[i])
        if i < len(efforts) and efforts:
            _acc_scalar(scalar_acc, f"{topic}/effort[{i}]", t, efforts[i])


def _extract_compressed_image(topic, t, msg, scalar_acc, msg_acc) -> None:
    """sensor_msgs/msg/CompressedImage → store raw bytes for lazy decode."""
    fmt = getattr(msg, "format", "jpeg")
    data = getattr(msg, "data", b"")
    if isinstance(data, (list, tuple)):
        data = bytes(data)
    # Store as (format, raw_bytes) tuple — ImagePanel decodes on demand
    msg_acc[topic].append((t, {"format": fmt, "data": data}))


def _extract_image(topic, t, msg, scalar_acc, msg_acc) -> None:
    """sensor_msgs/msg/Image → decode to numpy array."""
    width = getattr(msg, "width", 0)
    height = getattr(msg, "height", 0)
    encoding = getattr(msg, "encoding", "rgb8")
    data = getattr(msg, "data", b"")

    if isinstance(data, (list, tuple)):
        data = bytes(data)

    try:
        img = _decode_raw_image(data, width, height, encoding)
        msg_acc[topic].append((t, img))
    except Exception:
        msg_acc[topic].append((t, {"encoding": encoding, "width": width,
                                    "height": height, "data": data}))


def _extract_pose_stamped(topic, t, msg, scalar_acc, msg_acc) -> None:
    """geometry_msgs/msg/PoseStamped → extract position + orientation."""
    pose = getattr(msg, "pose", None)
    if pose is None:
        return
    pos = getattr(pose, "position", None)
    orient = getattr(pose, "orientation", None)
    if pos:
        _acc_scalar(scalar_acc, f"{topic}/pose.position.x", t, pos.x)
        _acc_scalar(scalar_acc, f"{topic}/pose.position.y", t, pos.y)
        _acc_scalar(scalar_acc, f"{topic}/pose.position.z", t, pos.z)
    if orient:
        _acc_scalar(scalar_acc, f"{topic}/pose.orientation.x", t, orient.x)
        _acc_scalar(scalar_acc, f"{topic}/pose.orientation.y", t, orient.y)
        _acc_scalar(scalar_acc, f"{topic}/pose.orientation.z", t, orient.z)
        _acc_scalar(scalar_acc, f"{topic}/pose.orientation.w", t, orient.w)


def _extract_odometry(topic, t, msg, scalar_acc, msg_acc) -> None:
    """nav_msgs/msg/Odometry → pose + twist scalars."""
    pose_ws = getattr(msg, "pose", None)
    if pose_ws:
        pose = getattr(pose_ws, "pose", None)
        if pose:
            pos = getattr(pose, "position", None)
            if pos:
                _acc_scalar(scalar_acc, f"{topic}/pose.position.x", t, pos.x)
                _acc_scalar(scalar_acc, f"{topic}/pose.position.y", t, pos.y)
                _acc_scalar(scalar_acc, f"{topic}/pose.position.z", t, pos.z)
            orient = getattr(pose, "orientation", None)
            if orient:
                _acc_scalar(scalar_acc, f"{topic}/pose.orientation.x", t, orient.x)
                _acc_scalar(scalar_acc, f"{topic}/pose.orientation.y", t, orient.y)
                _acc_scalar(scalar_acc, f"{topic}/pose.orientation.z", t, orient.z)
                _acc_scalar(scalar_acc, f"{topic}/pose.orientation.w", t, orient.w)

    twist_ws = getattr(msg, "twist", None)
    if twist_ws:
        twist = getattr(twist_ws, "twist", None)
        if twist:
            lin = getattr(twist, "linear", None)
            if lin:
                _acc_scalar(scalar_acc, f"{topic}/twist.linear.x", t, lin.x)
                _acc_scalar(scalar_acc, f"{topic}/twist.linear.y", t, lin.y)
                _acc_scalar(scalar_acc, f"{topic}/twist.linear.z", t, lin.z)
            ang = getattr(twist, "angular", None)
            if ang:
                _acc_scalar(scalar_acc, f"{topic}/twist.angular.x", t, ang.x)
                _acc_scalar(scalar_acc, f"{topic}/twist.angular.y", t, ang.y)
                _acc_scalar(scalar_acc, f"{topic}/twist.angular.z", t, ang.z)


def _extract_tf_message(topic, t, msg, scalar_acc, msg_acc) -> None:
    """tf2_msgs/msg/TFMessage → store as non-scalar for future use."""
    msg_acc[topic].append((t, msg))


def _extract_scalar_msg(topic, t, msg, scalar_acc, msg_acc) -> None:
    """std_msgs/msg/Float64 / Float32 / Int32 / Bool → single scalar."""
    val = getattr(msg, "data", None)
    if val is not None:
        _acc_scalar(scalar_acc, f"{topic}/data", t, float(val))


def _extract_generic(topic, t, msg, scalar_acc, msg_acc) -> None:
    """Generic fallback: recursively walk fields, extract numeric leaves."""
    _walk_fields(topic, t, msg, scalar_acc, msg_acc, depth=0)


# ---------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------

_EXTRACTORS: dict[str, _ExtractorFn] = {}


def _register_extractor(*type_names: str):
    def decorator(fn: _ExtractorFn) -> _ExtractorFn:
        for name in type_names:
            _EXTRACTORS[name] = fn
        return fn
    return decorator


# Register all specialised extractors
for _names, _fn in [
    (("sensor_msgs/msg/JointState", "sensor_msgs/JointState", "JointState"),
     _extract_joint_state),
    (("sensor_msgs/msg/CompressedImage", "sensor_msgs/CompressedImage", "CompressedImage"),
     _extract_compressed_image),
    (("sensor_msgs/msg/Image", "sensor_msgs/Image"),
     _extract_image),
    (("geometry_msgs/msg/PoseStamped", "geometry_msgs/PoseStamped"),
     _extract_pose_stamped),
    (("nav_msgs/msg/Odometry", "nav_msgs/Odometry"),
     _extract_odometry),
    (("tf2_msgs/msg/TFMessage", "tf2_msgs/TFMessage"),
     _extract_tf_message),
    (("std_msgs/msg/Float64", "std_msgs/msg/Float32",
      "std_msgs/msg/Int32", "std_msgs/msg/Int64",
      "std_msgs/msg/Bool",
      "std_msgs/Float64", "std_msgs/Float32",
      "std_msgs/Int32", "std_msgs/Int64", "std_msgs/Bool"),
     _extract_scalar_msg),
]:
    for _n in _names:
        _EXTRACTORS[_n] = _fn


def _get_extractor(msg_type: str) -> _ExtractorFn:
    return _EXTRACTORS.get(msg_type, _extract_generic)


# ---------------------------------------------------------------------------
# Generic field walker
# ---------------------------------------------------------------------------

_MAX_WALK_DEPTH = 8
_SKIP_FIELDS = frozenset({"header", "_header"})


def _walk_fields(
    prefix: str, t: float, obj: Any,
    scalar_acc: dict[str, _ScalarAccumulator],
    msg_acc: dict,
    depth: int,
) -> None:
    """Recursively extract numeric fields from a decoded ROS 2 message."""
    if depth > _MAX_WALK_DEPTH:
        return

    if isinstance(obj, SimpleNamespace):
        fields = vars(obj)
    elif isinstance(obj, dict):
        fields = obj
    else:
        return

    for name, value in fields.items():
        if name in _SKIP_FIELDS:
            continue
        path = f"{prefix}/{name}" if depth > 0 else f"{prefix}/{name}"

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            _acc_scalar(scalar_acc, path, t, float(value))
        elif isinstance(value, (list, tuple)):
            _walk_sequence(path, t, value, scalar_acc, msg_acc, depth)
        elif isinstance(value, (SimpleNamespace, dict)):
            _walk_fields(path, t, value, scalar_acc, msg_acc, depth + 1)


def _walk_sequence(
    prefix: str, t: float, seq: list | tuple,
    scalar_acc: dict[str, _ScalarAccumulator],
    msg_acc: dict,
    depth: int,
) -> None:
    """Walk a list/tuple field: numeric arrays → indexed scalars."""
    if not seq:
        return
    first = seq[0]
    if isinstance(first, (int, float)) and not isinstance(first, bool):
        for i, v in enumerate(seq):
            _acc_scalar(scalar_acc, f"{prefix}[{i}]", t, float(v))
    elif isinstance(first, (SimpleNamespace, dict)):
        for i, item in enumerate(seq):
            _walk_fields(f"{prefix}[{i}]", t, item, scalar_acc, msg_acc, depth + 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _acc_scalar(acc: dict[str, _ScalarAccumulator], path: str, t: float, v: float) -> None:
    if path not in acc:
        acc[path] = _ScalarAccumulator()
    acc[path].append(t, v)


def _extract_json_joint_state(topic, t, msg, scalar_acc) -> None:
    """Handle the JSON joint-state format from the test generator."""
    names = msg.get("name", [])
    positions = msg.get("position", [])
    for i, _name in enumerate(names):
        if i < len(positions):
            _acc_scalar(scalar_acc, f"{topic}/position[{i}]", t, positions[i])


def _extract_generic_dict(topic, t, msg, scalar_acc, msg_acc) -> None:
    """Handle a generic JSON dict — extract numeric fields."""
    _walk_fields(topic, t, msg, scalar_acc, msg_acc, depth=0)


# ---------------------------------------------------------------------------
# Image decoding
# ---------------------------------------------------------------------------

_ENCODING_TO_DTYPE: dict[str, tuple[np.dtype, int]] = {
    "rgb8": (np.uint8, 3),
    "bgr8": (np.uint8, 3),
    "rgba8": (np.uint8, 4),
    "bgra8": (np.uint8, 4),
    "mono8": (np.uint8, 1),
    "8UC1": (np.uint8, 1),
    "8UC3": (np.uint8, 3),
    "16UC1": (np.uint16, 1),
    "32FC1": (np.float32, 1),
}


def _decode_raw_image(data: bytes, width: int, height: int, encoding: str) -> np.ndarray:
    """Decode raw image bytes to a numpy array."""
    dtype, channels = _ENCODING_TO_DTYPE.get(encoding, (np.uint8, 3))
    arr = np.frombuffer(data, dtype=dtype)

    if channels == 1:
        img = arr.reshape(height, width)
    else:
        img = arr.reshape(height, width, channels)

    # Convert BGR to RGB for display
    if encoding in ("bgr8", "bgra8"):
        img = img[..., ::-1].copy() if encoding == "bgr8" else img[..., [2, 1, 0, 3]].copy()

    return img
