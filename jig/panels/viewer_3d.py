"""Viewer3DPanel — MuJoCo offscreen 3D viewer with model loading and config."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QLabel,
    QPushButton,
    QWidget,
)

from jig.core.app_context import AppContext
from jig.panels.base import PanelBase
from jig.panels.registry import PanelRegistry

try:
    import mujoco

    HAS_MUJOCO = True
except ImportError:
    HAS_MUJOCO = False

ARM_MJCF = """\
<mujoco model="arm7">
  <option gravity="0 0 -9.81"/>
  <visual><global offwidth="640" offheight="480"/></visual>
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
              <joint name="joint4" type="hinge" axis="0 -1 0" range="-3.07 0.07"/>
              <geom type="capsule" fromto="0 0 0 0 0 0.384" size="0.04"
                    rgba="0.85 0.85 0.9 1"/>
              <body name="link5" pos="0 0 0.384">
                <joint name="joint5" type="hinge" axis="0 0 1" range="-2.9 2.9"/>
                <geom type="capsule" fromto="0 0 0 0 0 0.088" size="0.035"
                      rgba="0.9 0.9 0.95 1"/>
                <body name="link6" pos="0 0 0.088">
                  <joint name="joint6" type="hinge" axis="0 1 0" range="-0.02 3.75"/>
                  <geom type="capsule" fromto="0 0 0 0 0 0.107" size="0.035"
                        rgba="0.85 0.85 0.9 1"/>
                  <body name="link7" pos="0 0 0.107">
                    <joint name="joint7" type="hinge" axis="0 0 1" range="-2.9 2.9"/>
                    <geom type="cylinder" size="0.045 0.025" rgba="0.95 0.6 0.2 1"/>
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

# Default joint series paths for the built-in test model
_JOINT_SERIES = [f"/joint_states/position[{i}]" for i in range(7)]

# Button style shared across toolbar


@PanelRegistry.register
class Viewer3DPanel(PanelBase):
    panel_type_name = "3D Viewer"
    panel_icon = "\U0001f3ae"  # 🎮

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.setMinimumSize(320, 240)

        self._model_path: str = ""  # empty = built-in model
        self._joint_topic: str = "/joint_states"
        self._show_frames = True
        self._show_grid = True
        self._mj_ok = False
        self._last_mouse_pos = None
        self._joint_series_paths: list[str] = list(_JOINT_SERIES)

        # -- Toolbar controls --
        self._setup_toolbar()

        # -- Render area --
        self._image_label = QLabel("3D Viewer")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: #161b2e;")
        self.add_content_widget(self._image_label, stretch=1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("panelStatus")
        self._status_label.setStyleSheet("font-size: 10px; color: #808080; padding: 2px 6px;")
        self.add_content_widget(self._status_label)

        # -- Init MuJoCo --
        if HAS_MUJOCO:
            try:
                self._init_mujoco_from_xml(ARM_MJCF)
                self._mj_ok = True
            except Exception as e:
                self._status_label.setText(f"MuJoCo init error: {e}")
        else:
            self._status_label.setText("mujoco not installed")

        self._render()

    def _setup_toolbar(self) -> None:
        # Load model button
        load_btn = QPushButton("Load Model")
        load_btn.setToolTip("Load URDF or MJCF model file")
        load_btn.clicked.connect(self._load_model_dialog)
        self.toolbar.add_widget(load_btn)

        # Reset camera button
        reset_btn = QPushButton("Reset Camera")
        reset_btn.clicked.connect(self._reset_camera)
        self.toolbar.add_widget(reset_btn)

        self.toolbar.add_separator()

        # Joint topic selector
        topic_label = QLabel("Topic:")
        self.toolbar.add_widget(topic_label)

        self._topic_combo = QComboBox()
        self._topic_combo.setFixedWidth(140)
        self._topic_combo.setToolTip("JointState topic to drive the model")
        self._topic_combo.currentTextChanged.connect(self._on_topic_changed)
        self.toolbar.add_widget(self._topic_combo)

        self.toolbar.add_separator()

        # Frames toggle
        self._frames_cb = QCheckBox("Frames")
        self._frames_cb.setChecked(True)
        self._frames_cb.toggled.connect(self._on_frames_toggled)
        self.toolbar.add_widget(self._frames_cb)

        # Grid toggle
        self._grid_cb = QCheckBox("Grid")
        self._grid_cb.setChecked(True)
        self._grid_cb.toggled.connect(self._on_grid_toggled)
        self.toolbar.add_widget(self._grid_cb)

        # Populate topics when data arrives
        for session in self.ctx.sessions:
            session.data_store.data_changed.connect(self._refresh_topics)

    # -- Model loading -------------------------------------------------------

    def _load_model_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Model",  "",
            "Model Files (*.xml *.mjcf *.urdf);;All Files (*)",
        )
        if path:
            self._load_model_file(path)

    def _load_model_file(self, path: str) -> None:
        if not HAS_MUJOCO:
            return
        try:
            model = mujoco.MjModel.from_xml_path(path)
            self._model_path = path
            self._cleanup_mujoco()
            self._model = model
            self._mj_data = mujoco.MjData(self._model)
            self._renderer = mujoco.Renderer(self._model, height=480, width=640)
            self._reset_camera_state()
            self._scene_opt = mujoco.MjvOption()
            self._update_scene_options()
            self._mj_ok = True
            self._rebuild_joint_paths()
            self.toolbar.title = Path(path).stem
            self._status_label.setText(f"Loaded: {Path(path).name}")
            self._render()
        except Exception as e:
            self._status_label.setText(f"Load error: {e}")

    def _init_mujoco_from_xml(self, xml: str) -> None:
        self._model = mujoco.MjModel.from_xml_string(xml)
        self._mj_data = mujoco.MjData(self._model)
        self._renderer = mujoco.Renderer(self._model, height=480, width=640)
        self._reset_camera_state()
        self._scene_opt = mujoco.MjvOption()
        self._update_scene_options()

    def _cleanup_mujoco(self) -> None:
        if hasattr(self, "_renderer"):
            self._renderer.close()

    def _reset_camera_state(self) -> None:
        self._camera = mujoco.MjvCamera()
        self._camera.type = mujoco.mjtCamera.mjCAMERA_FREE
        self._camera.distance = 2.5
        self._camera.azimuth = 135.0
        self._camera.elevation = -25.0
        self._camera.lookat[:] = [0.0, 0.0, 0.6]

    def _reset_camera(self) -> None:
        if self._mj_ok:
            self._reset_camera_state()
            self._render()

    # -- Topic binding -------------------------------------------------------

    def _refresh_topics(self) -> None:
        ds = self.ctx.active_data_store
        if ds is None:
            return
        # Find topics that look like JointState (have position fields)
        joint_topics = []
        for name, info in ds.topics.items():
            if any("position" in f for f in info.fields):
                joint_topics.append(name)
        current = self._topic_combo.currentText()
        self._topic_combo.blockSignals(True)
        self._topic_combo.clear()
        self._topic_combo.addItems(joint_topics)
        if current in joint_topics:
            self._topic_combo.setCurrentText(current)
        elif joint_topics:
            self._topic_combo.setCurrentIndex(0)
            self._joint_topic = joint_topics[0]
        self._topic_combo.blockSignals(False)
        self._rebuild_joint_paths()

    def _on_topic_changed(self, topic: str) -> None:
        self._joint_topic = topic
        self._rebuild_joint_paths()
        self._render()

    def _rebuild_joint_paths(self) -> None:
        """Rebuild joint series paths from the selected topic."""
        if not self._mj_ok:
            return
        nq = self._model.nq
        self._joint_series_paths = [
            f"{self._joint_topic}/position[{i}]" for i in range(nq)
        ]

    # -- Frames / Grid toggles -----------------------------------------------

    def _on_frames_toggled(self, checked: bool) -> None:
        self._show_frames = checked
        if self._mj_ok:
            self._update_scene_options()
            self._render()

    def _on_grid_toggled(self, checked: bool) -> None:
        self._show_grid = checked
        if self._mj_ok:
            self._render()

    def _update_scene_options(self) -> None:
        if self._show_frames:
            self._scene_opt.frame = mujoco.mjtFrame.mjFRAME_BODY
        else:
            self._scene_opt.frame = mujoco.mjtFrame.mjFRAME_NONE

    # -- Rendering -----------------------------------------------------------

    def _render(self) -> None:
        if not self._mj_ok:
            return

        t0 = time.perf_counter()
        t = self.ctx.timeline.current_time
        ds = self.ctx.active_data_store

        if ds is not None:
            for i, path in enumerate(self._joint_series_paths):
                if i < self._model.nq:
                    self._mj_data.qpos[i] = ds.get_scalar_at(path, t)

        mujoco.mj_forward(self._model, self._mj_data)
        self._renderer.update_scene(
            self._mj_data, camera=self._camera, scene_option=self._scene_opt
        )
        rgb = self._renderer.render()
        dt_ms = (time.perf_counter() - t0) * 1000

        h, w, _ = rgb.shape
        rgb_c = np.ascontiguousarray(rgb)
        qimg = QImage(rgb_c.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg.copy())

        self._image_label.setPixmap(
            pixmap.scaled(
                self._image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self._status_label.setText(
            f"Render: {dt_ms:.1f} ms  ({1000 / max(dt_ms, 0.1):.0f} fps)"
        )

    # -- PanelBase interface -------------------------------------------------

    def on_time_changed(self, t: float) -> None:
        self._render()

    def get_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "model_path": self._model_path,
            "joint_topic": self._joint_topic,
            "show_frames": self._show_frames,
            "show_grid": self._show_grid,
        }
        if self._mj_ok:
            state["camera"] = {
                "distance": self._camera.distance,
                "azimuth": self._camera.azimuth,
                "elevation": self._camera.elevation,
                "lookat": list(self._camera.lookat),
            }
        return state

    def set_state(self, state: dict[str, Any]) -> None:
        # Restore model
        model_path = state.get("model_path", "")
        if model_path and Path(model_path).exists():
            self._load_model_file(model_path)

        # Restore topic
        topic = state.get("joint_topic", "")
        if topic:
            self._joint_topic = topic
            self._topic_combo.setCurrentText(topic)
            self._rebuild_joint_paths()

        # Restore toggles
        self._show_frames = state.get("show_frames", True)
        self._frames_cb.setChecked(self._show_frames)
        self._show_grid = state.get("show_grid", True)
        self._grid_cb.setChecked(self._show_grid)

        # Restore camera
        cam = state.get("camera", {})
        if cam and self._mj_ok:
            self._camera.distance = cam.get("distance", self._camera.distance)
            self._camera.azimuth = cam.get("azimuth", self._camera.azimuth)
            self._camera.elevation = cam.get("elevation", self._camera.elevation)
            lookat = cam.get("lookat")
            if lookat:
                self._camera.lookat[:] = lookat

    # -- Mouse orbit / pan / zoom -------------------------------------------

    def mousePressEvent(self, event) -> None:
        self._last_mouse_pos = event.position()

    def mouseMoveEvent(self, event) -> None:
        if self._last_mouse_pos is None or not self._mj_ok:
            return
        dx = event.position().x() - self._last_mouse_pos.x()
        dy = event.position().y() - self._last_mouse_pos.y()
        self._last_mouse_pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self._camera.azimuth += dx * 0.5
            self._camera.elevation = float(
                np.clip(self._camera.elevation - dy * 0.5, -90, 90)
            )
            self._render()
        elif event.buttons() & Qt.MouseButton.RightButton:
            self._camera.lookat[0] -= dx * 0.003
            self._camera.lookat[2] += dy * 0.003
            self._render()

    def mouseReleaseEvent(self, event) -> None:
        self._last_mouse_pos = None

    def wheelEvent(self, event) -> None:
        if not self._mj_ok:
            return
        delta = event.angleDelta().y()
        self._camera.distance *= 1.0 - delta * 0.001
        self._camera.distance = max(0.1, self._camera.distance)
        self._render()
