# Jig — Project Instructions for Claude Code

## Project Context

**Jig** is a next-generation desktop GUI for robotics engineers. It unifies simulation, hardware experiments, and log visualization into a single tool. Spiritual successor to IHMC's SCS2, rebuilt on Python/C++ with ROS 2 and MuJoCo.

- **Notion hub**: https://www.notion.so/31d8f2ec964481ffbf22c93e7c0582c2
- **Repo**: https://github.com/SylvainBertrand/jig

## Core Principles

1. Simulation is a first-class citizen (MuJoCo + ros2_control)
2. Same GUI for sim, hardware, and log playback (Session abstraction)
3. Real-time variable tuning (entry boxes, sliders)
4. ROS 2 native (topics, services, params, MCAP logs)
5. Python-first, C++ where needed (pybind11 for perf-critical paths)
6. Open format, open ecosystem (MCAP, URDF, MJCF)

## Tech Stack

- Physics: MuJoCo
- Control: ros2_control
- Communication: ROS 2 (DDS)
- Logs: MCAP
- Language: Python + C++ (pybind11)
- GUI framework: TBD (Qt6 vs Web vs Tauri)

## Conventions

- License: Apache 2.0
- Branch strategy: feature branches off `main`, PRs required
- Python style: follow PEP 8
- C++ style: follow Google C++ Style Guide
