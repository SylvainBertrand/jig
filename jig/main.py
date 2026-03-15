"""Entry point for Jig."""

from __future__ import annotations

import sys
from pathlib import Path

from jig.app import JigApp


def main() -> None:
    app = JigApp(sys.argv)

    args = sys.argv[1:]

    if args and args[0].endswith(".mcap"):
        # Load a real MCAP file
        app.load_mcap(Path(args[0]))
    elif "--ros2" in args:
        # Generate ROS 2 CDR-encoded test data
        app.generate_and_load_test_data(fmt="ros2")
    else:
        # Generate lightweight JSON test data (default)
        app.generate_and_load_test_data()

    # Add default panels
    app.window.dock_manager.add_panel("3D Viewer")
    app.window.dock_manager.add_panel("Chart")
    app.window.dock_manager.add_panel("Image")

    sys.exit(app.run())


if __name__ == "__main__":
    main()
