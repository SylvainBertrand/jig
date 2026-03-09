"""Generate synthetic MCAP test data for development.

Ported from the spike with minimal changes.
"""

from __future__ import annotations

import io
import json
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


def generate_mcap(path: str) -> str:
    """Generate a synthetic MCAP file with joint states and images."""
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
    print(f"MCAP generation:  {elapsed:.2f}s  ({path})")
    return path
