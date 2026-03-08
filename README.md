# Jig

Robotics simulation, visualization, and hardware experiment workbench.

Jig is a desktop GUI for robotics engineers to intuitively interface with **simulation**, **hardware experiments**, and **log visualization** — all from a single tool. Spiritual successor to [IHMC's SCS2](https://github.com/ihmcrobotics/simulation-construction-set-2), rebuilt on a modern stack (Python/C++, ROS 2, MuJoCo).

## Key Features (Planned)

- Tight simulation loop integration (MuJoCo + ros2_control)
- Real-time variable tuning & entry boxes during sim/hardware runs
- Shared-memory variable buffer with full playback/scrubbing
- Grouped variable search & charting
- 2D overhead plotter + 3D scene in one app
- Hardware experiment mode with same GUI as simulation
- MCAP log loading, ROS 2 native

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Physics | MuJoCo |
| Robot control | ros2_control |
| Communication | ROS 2 (DDS) |
| Log format | MCAP |
| Language | Python + C++ (pybind11) |

## License

[Apache License 2.0](LICENSE)
