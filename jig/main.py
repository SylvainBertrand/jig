"""Entry point for Jig."""

from __future__ import annotations

import sys
from pathlib import Path

from jig.app import JigApp


def main() -> None:
    app = JigApp(sys.argv)

    # If an MCAP path was passed as argument, load it
    args = sys.argv[1:]
    if args and args[0].endswith(".mcap"):
        app.load_mcap(Path(args[0]))
    else:
        # Generate synthetic test data for development
        app.generate_and_load_test_data()

    # Add default panels
    app.window.dock_manager.add_panel("3D Viewer")
    app.window.dock_manager.add_panel("Chart")
    app.window.dock_manager.add_panel("Image")

    sys.exit(app.run())


if __name__ == "__main__":
    main()
