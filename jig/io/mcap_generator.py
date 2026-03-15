"""Generate synthetic MCAP test data for development.

Supports two output formats:
- ``"json"`` (default): lightweight JSON-encoded messages, fast to generate.
- ``"ros2"``: CDR-encoded messages with proper ROS 2 schemas, exercises the
  full deserialization pipeline used for real bag files.
"""

from __future__ import annotations

import io
import json
import struct
import time

import numpy as np
from PIL import Image as PILImage
from mcap.writer import Writer

DURATION = 10.0
JOINT_RATE = 1000
IMAGE_RATE = 30
IMAGE_W, IMAGE_H = 640, 480
JOINT_NAMES = [f"joint{i + 1}" for i in range(7)]
JOINT_FREQS = [0.3, 0.5, 0.7, 0.4, 0.6, 0.8, 0.35]
POSE_RATE = 50


def make_frame(t: float) -> bytes:
    """Create a colorful test frame, return JPEG bytes."""
    phase = t / DURATION
    y = np.linspace(0, 1, IMAGE_H, dtype=np.float32).reshape(-1, 1)
    x = np.linspace(0, 1, IMAGE_W, dtype=np.float32).reshape(1, -1)

    r = np.sin(2 * np.pi * (phase + x)) * 127 + 128
    g = np.sin(2 * np.pi * (phase * 1.5 + y + 0.33)) * 127 + 128
    b = np.sin(2 * np.pi * (phase * 0.7 + x + y + 0.66)) * 127 + 128

    img = np.stack(
        [
            np.broadcast_to(r, (IMAGE_H, IMAGE_W)),
            np.broadcast_to(g, (IMAGE_H, IMAGE_W)),
            np.broadcast_to(b, (IMAGE_H, IMAGE_W)),
        ],
        axis=-1,
    ).astype(np.uint8)

    buf = io.BytesIO()
    PILImage.fromarray(img).save(buf, format="JPEG", quality=60)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# CDR encoding helpers (little-endian, XCDR1)
# ---------------------------------------------------------------------------

def _cdr_header() -> bytes:
    """4-byte CDR encapsulation header (LE, options=0)."""
    return b"\x00\x01\x00\x00"


def _pad_to(buf: bytearray, alignment: int) -> None:
    """Pad buffer so the next write is aligned (relative to CDR data start at byte 4)."""
    # CDR alignment is relative to the start of the serialized data,
    # which begins after the 4-byte encapsulation header.
    pos = len(buf) - 4  # position relative to data start
    rem = pos % alignment
    if rem:
        buf.extend(b"\x00" * (alignment - rem))


def _cdr_encode_joint_state(
    sec: int, nanosec: int, names: list[str],
    positions: list[float], velocities: list[float], efforts: list[float],
) -> bytes:
    """Encode a sensor_msgs/msg/JointState in CDR."""
    buf = bytearray(_cdr_header())

    # Header.stamp (sec: uint32, nanosec: uint32)
    buf.extend(struct.pack("<II", sec, nanosec))
    # Header.frame_id (string: uint32 len + data + null)
    frame_id = b"\x00"
    buf.extend(struct.pack("<I", len(frame_id)))
    buf.extend(frame_id)

    # name[] (sequence of strings)
    _pad_to(buf, 4)
    buf.extend(struct.pack("<I", len(names)))
    for name in names:
        _pad_to(buf, 4)
        encoded = name.encode("utf-8") + b"\x00"
        buf.extend(struct.pack("<I", len(encoded)))
        buf.extend(encoded)

    # position[] (sequence of float64)
    _pad_to(buf, 4)
    buf.extend(struct.pack("<I", len(positions)))
    _pad_to(buf, 8)
    for v in positions:
        buf.extend(struct.pack("<d", v))

    # velocity[]
    _pad_to(buf, 4)
    buf.extend(struct.pack("<I", len(velocities)))
    _pad_to(buf, 8)
    for v in velocities:
        buf.extend(struct.pack("<d", v))

    # effort[]
    _pad_to(buf, 4)
    buf.extend(struct.pack("<I", len(efforts)))
    _pad_to(buf, 8)
    for v in efforts:
        buf.extend(struct.pack("<d", v))

    return bytes(buf)


def _cdr_encode_compressed_image(
    sec: int, nanosec: int, fmt: str, data: bytes,
) -> bytes:
    """Encode a sensor_msgs/msg/CompressedImage in CDR."""
    buf = bytearray(_cdr_header())

    # Header.stamp
    buf.extend(struct.pack("<II", sec, nanosec))
    # Header.frame_id
    frame_id = b"camera\x00"
    buf.extend(struct.pack("<I", len(frame_id)))
    buf.extend(frame_id)

    # format (string)
    _pad_to(buf, 4)
    fmt_bytes = fmt.encode("utf-8") + b"\x00"
    buf.extend(struct.pack("<I", len(fmt_bytes)))
    buf.extend(fmt_bytes)

    # data (sequence<uint8>)
    _pad_to(buf, 4)
    buf.extend(struct.pack("<I", len(data)))
    buf.extend(data)

    return bytes(buf)


def _cdr_encode_pose_stamped(
    sec: int, nanosec: int,
    x: float, y: float, z: float,
    qx: float, qy: float, qz: float, qw: float,
) -> bytes:
    """Encode a geometry_msgs/msg/PoseStamped in CDR."""
    buf = bytearray(_cdr_header())

    # Header.stamp
    buf.extend(struct.pack("<II", sec, nanosec))
    # Header.frame_id
    frame_id = b"world\x00"
    buf.extend(struct.pack("<I", len(frame_id)))
    buf.extend(frame_id)

    # Pose.position (Point: 3x float64)
    _pad_to(buf, 8)
    buf.extend(struct.pack("<ddd", x, y, z))
    # Pose.orientation (Quaternion: 4x float64)
    buf.extend(struct.pack("<dddd", qx, qy, qz, qw))

    return bytes(buf)


# ---------------------------------------------------------------------------
# ROS 2 message definitions (ros2msg format)
# ---------------------------------------------------------------------------

_JOINT_STATE_SCHEMA = """\
std_msgs/Header header
string[] name
float64[] position
float64[] velocity
float64[] effort

===
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id

===
MSG: builtin_interfaces/Time
uint32 sec
uint32 nanosec
"""

_COMPRESSED_IMAGE_SCHEMA = """\
std_msgs/Header header
string format
uint8[] data

===
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id

===
MSG: builtin_interfaces/Time
uint32 sec
uint32 nanosec
"""

_POSE_STAMPED_SCHEMA = """\
std_msgs/Header header
geometry_msgs/Pose pose

===
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id

===
MSG: builtin_interfaces/Time
uint32 sec
uint32 nanosec

===
MSG: geometry_msgs/Pose
geometry_msgs/Point position
geometry_msgs/Quaternion orientation

===
MSG: geometry_msgs/Point
float64 x
float64 y
float64 z

===
MSG: geometry_msgs/Quaternion
float64 x
float64 y
float64 z
float64 w
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_mcap(path: str, fmt: str = "json") -> str:
    """Generate a synthetic MCAP file.

    Args:
        path: Output file path.
        fmt: ``"json"`` for lightweight JSON encoding (original behaviour),
             ``"ros2"`` for CDR-encoded messages with proper ROS 2 schemas.
    """
    if fmt == "ros2":
        return _generate_ros2_mcap(path)
    return _generate_json_mcap(path)


def _generate_json_mcap(path: str) -> str:
    """Original JSON-encoded generator (fast, for quick dev iteration)."""
    t0 = time.perf_counter()

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start(profile="jig", library="jig")

        joint_schema_id = writer.register_schema(
            name="JointState",
            encoding="jsonschema",
            data=json.dumps({"type": "object"}).encode(),
        )
        image_schema_id = writer.register_schema(
            name="CompressedImage",
            encoding="raw",
            data=b"jpeg",
        )

        joint_ch = writer.register_channel(
            schema_id=joint_schema_id,
            topic="/joint_states",
            message_encoding="json",
        )
        image_ch = writer.register_channel(
            schema_id=image_schema_id,
            topic="/camera/image_raw",
            message_encoding="raw",
        )

        num_joints = int(DURATION * JOINT_RATE)
        for i in range(num_joints):
            t = i / JOINT_RATE
            ts_ns = int(t * 1e9)
            positions = [
                float(np.sin(2 * np.pi * freq * t + j * 0.5))
                for j, freq in enumerate(JOINT_FREQS)
            ]
            msg = json.dumps({"name": JOINT_NAMES, "position": positions}).encode()
            writer.add_message(
                channel_id=joint_ch, log_time=ts_ns, publish_time=ts_ns, data=msg
            )

        num_images = int(DURATION * IMAGE_RATE)
        for i in range(num_images):
            t = i / IMAGE_RATE
            ts_ns = int(t * 1e9)
            writer.add_message(
                channel_id=image_ch,
                log_time=ts_ns,
                publish_time=ts_ns,
                data=make_frame(t),
            )

        writer.finish()

    elapsed = time.perf_counter() - t0
    print(f"MCAP generation (json): {elapsed:.2f}s  ({path})")
    return path


def _generate_ros2_mcap(path: str) -> str:
    """CDR-encoded generator with proper ROS 2 schemas."""
    t0 = time.perf_counter()

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.start(profile="ros2", library="jig")

        # Register schemas
        joint_schema_id = writer.register_schema(
            name="sensor_msgs/msg/JointState",
            encoding="ros2msg",
            data=_JOINT_STATE_SCHEMA.encode(),
        )
        image_schema_id = writer.register_schema(
            name="sensor_msgs/msg/CompressedImage",
            encoding="ros2msg",
            data=_COMPRESSED_IMAGE_SCHEMA.encode(),
        )
        pose_schema_id = writer.register_schema(
            name="geometry_msgs/msg/PoseStamped",
            encoding="ros2msg",
            data=_POSE_STAMPED_SCHEMA.encode(),
        )

        # Register channels
        joint_ch = writer.register_channel(
            schema_id=joint_schema_id,
            topic="/joint_states",
            message_encoding="cdr",
        )
        image_ch = writer.register_channel(
            schema_id=image_schema_id,
            topic="/camera/compressed",
            message_encoding="cdr",
        )
        pose_ch = writer.register_channel(
            schema_id=pose_schema_id,
            topic="/robot/pose",
            message_encoding="cdr",
        )

        # Joint state messages
        num_joints = int(DURATION * JOINT_RATE)
        for i in range(num_joints):
            t = i / JOINT_RATE
            ts_ns = int(t * 1e9)
            sec = int(t)
            nanosec = int((t - sec) * 1e9)
            positions = [
                float(np.sin(2 * np.pi * freq * t + j * 0.5))
                for j, freq in enumerate(JOINT_FREQS)
            ]
            velocities = [
                float(np.cos(2 * np.pi * freq * t + j * 0.5) * 2 * np.pi * freq)
                for j, freq in enumerate(JOINT_FREQS)
            ]
            cdr = _cdr_encode_joint_state(
                sec, nanosec, JOINT_NAMES, positions, velocities, efforts=[0.0] * 7,
            )
            writer.add_message(
                channel_id=joint_ch, log_time=ts_ns, publish_time=ts_ns, data=cdr,
            )

        # Compressed image messages
        num_images = int(DURATION * IMAGE_RATE)
        for i in range(num_images):
            t = i / IMAGE_RATE
            ts_ns = int(t * 1e9)
            sec = int(t)
            nanosec = int((t - sec) * 1e9)
            cdr = _cdr_encode_compressed_image(sec, nanosec, "jpeg", make_frame(t))
            writer.add_message(
                channel_id=image_ch, log_time=ts_ns, publish_time=ts_ns, data=cdr,
            )

        # Pose messages (circular trajectory)
        num_poses = int(DURATION * POSE_RATE)
        for i in range(num_poses):
            t = i / POSE_RATE
            ts_ns = int(t * 1e9)
            sec = int(t)
            nanosec = int((t - sec) * 1e9)
            angle = 2 * np.pi * t / DURATION
            cdr = _cdr_encode_pose_stamped(
                sec, nanosec,
                x=float(np.cos(angle) * 0.5),
                y=float(np.sin(angle) * 0.5),
                z=0.3,
                qx=0.0, qy=0.0,
                qz=float(np.sin(angle / 2)),
                qw=float(np.cos(angle / 2)),
            )
            writer.add_message(
                channel_id=pose_ch, log_time=ts_ns, publish_time=ts_ns, data=cdr,
            )

        writer.finish()

    elapsed = time.perf_counter() - t0
    print(f"MCAP generation (ros2): {elapsed:.2f}s  ({path})")
    return path
