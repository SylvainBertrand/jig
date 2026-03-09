"""3D viewer panel using MuJoCo offscreen rendering."""

import time

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jig_spike_qt.data_store import DataStore

try:
    import mujoco

    HAS_MUJOCO = True
except ImportError:
    HAS_MUJOCO = False

# Simple 7-DOF arm MJCF (Panda-like proportions)
ARM_MJCF = """\
<mujoco model="arm7">
  <option gravity="0 0 -9.81"/>
  <visual>
    <global offwidth="640" offheight="480"/>
  </visual>
  <worldbody>
    <light pos="0.5 -0.5 2" dir="-0.2 0.2 -1" diffuse="0.8 0.8 0.8"/>
    <light pos="-0.5 0.5 2" dir="0.2 -0.2 -1" diffuse="0.4 0.4 0.4"/>
    <geom type="plane" size="2 2 0.01" rgba="0.25 0.25 0.3 1"/>
    <body name="base" pos="0 0 0.05">
      <geom type="cylinder" size="0.08 0.05" rgba="0.3 0.3 0.35 1"/>
      <body name="link1" pos="0 0 0.05">
        <joint name="joint1" type="hinge" axis="0 0 1" range="-2.9 2.9"/>
        <geom type="capsule" fromto="0 0 0 0 0 0.333" size="0.045"
              rgba="0.9 0.9 0.95 1"/>
        <body name="link2" pos="0 0 0.333">
          <joint name="joint2" type="hinge" axis="0 1 0" range="-1.76 1.76"/>
          <geom type="capsule" fromto="0 0 0 0 0 0.316" size="0.045"
                rgba="0.85 0.85 0.9 1"/>
          <body name="link3" pos="0 0 0.316">
            <joint name="joint3" type="hinge" axis="0 0 1" range="-2.9 2.9"/>
            <geom type="capsule" fromto="0 0 0 0 0 0.083" size="0.04"
                  rgba="0.9 0.9 0.95 1"/>
            <body name="link4" pos="0 0 0.083">
              <joint name="joint4" type="hinge" axis="0 -1 0"
                     range="-3.07 0.07"/>
              <geom type="capsule" fromto="0 0 0 0 0 0.384" size="0.04"
                    rgba="0.85 0.85 0.9 1"/>
              <body name="link5" pos="0 0 0.384">
                <joint name="joint5" type="hinge" axis="0 0 1"
                       range="-2.9 2.9"/>
                <geom type="capsule" fromto="0 0 0 0 0 0.088" size="0.035"
                      rgba="0.9 0.9 0.95 1"/>
                <body name="link6" pos="0 0 0.088">
                  <joint name="joint6" type="hinge" axis="0 1 0"
                         range="-0.02 3.75"/>
                  <geom type="capsule" fromto="0 0 0 0 0 0.107" size="0.035"
                        rgba="0.85 0.85 0.9 1"/>
                  <body name="link7" pos="0 0 0.107">
                    <joint name="joint7" type="hinge" axis="0 0 1"
                           range="-2.9 2.9"/>
                    <geom type="cylinder" size="0.045 0.025"
                          rgba="0.95 0.6 0.2 1"/>
                  </body>
                </body>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>
  </worldbody>
</mujoco>
"""


class Viewer3DPanel(QWidget):
    def __init__(self, data_store: DataStore, parent=None):
        super().__init__(parent)
        self.data_store = data_store
        self.setMinimumSize(320, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel("3D Viewer")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #1a1a2e;")
        layout.addWidget(self.image_label, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        layout.addWidget(self.status_label)

        self._mj_ok = False
        self._last_pos = None

        if HAS_MUJOCO:
            try:
                self._init_mujoco()
                self._mj_ok = True
            except Exception as e:
                self.status_label.setText(f"MuJoCo init error: {e}")
        else:
            self.status_label.setText("mujoco not installed")

        self.data_store.timeline_changed.connect(self._on_timeline)
        self._render()

    def _init_mujoco(self):
        self.model = mujoco.MjModel.from_xml_string(ARM_MJCF)
        self.mj_data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=480, width=640)

        self.camera = mujoco.MjvCamera()
        self.camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self.camera.distance = 2.5
        self.camera.azimuth = 135.0
        self.camera.elevation = -25.0
        self.camera.lookat[:] = [0.0, 0.0, 0.6]

        self.scene_opt = mujoco.MjvOption()
        self.scene_opt.frame = mujoco.mjtFrame.mjFRAME_BODY

    def _render(self):
        if not self._mj_ok:
            return

        t0 = time.perf_counter()

        positions = self.data_store.get_joint_positions()
        n = min(len(positions), self.model.nq)
        self.mj_data.qpos[:n] = positions[:n]
        mujoco.mj_forward(self.model, self.mj_data)

        self.renderer.update_scene(
            self.mj_data, camera=self.camera, scene_option=self.scene_opt
        )
        rgb = self.renderer.render()

        dt_ms = (time.perf_counter() - t0) * 1000

        # Convert to QPixmap
        h, w, _ = rgb.shape
        rgb_c = np.ascontiguousarray(rgb)
        qimg = QImage(rgb_c.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg.copy())  # copy to decouple from numpy

        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.status_label.setText(
            f"Render: {dt_ms:.1f} ms  ({1000 / max(dt_ms, 0.1):.0f} fps)"
        )

    def _on_timeline(self, t: float):
        self._render()

    # --- Mouse orbit / pan / zoom ---

    def mousePressEvent(self, event):
        self._last_pos = event.position()

    def mouseMoveEvent(self, event):
        if self._last_pos is None or not self._mj_ok:
            return
        dx = event.position().x() - self._last_pos.x()
        dy = event.position().y() - self._last_pos.y()
        self._last_pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self.camera.azimuth += dx * 0.5
            self.camera.elevation = float(
                np.clip(self.camera.elevation - dy * 0.5, -90, 90)
            )
            self._render()
        elif event.buttons() & Qt.MouseButton.RightButton:
            self.camera.lookat[0] -= dx * 0.003
            self.camera.lookat[2] += dy * 0.003
            self._render()

    def mouseReleaseEvent(self, event):
        self._last_pos = None

    def wheelEvent(self, event):
        if not self._mj_ok:
            return
        delta = event.angleDelta().y()
        self.camera.distance *= 1.0 - delta * 0.001
        self.camera.distance = max(0.1, self.camera.distance)
        self._render()
