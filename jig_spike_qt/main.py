"""Entry point for the Jig Qt6 spike."""

import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from PySide6.QtWidgets import QApplication

from jig_spike_qt.data_store import DataStore
from jig_spike_qt.mcap_generator import generate_mcap
from jig_spike_qt.panel_shell import MainWindow


def main():
    mcap_path = str(Path(tempfile.gettempdir()) / "jig_spike_test.mcap")

    print("=" * 50)
    print("Jig Qt6 Spike \u2014 Performance Metrics")
    print("=" * 50)

    # Generate synthetic MCAP
    generate_mcap(mcap_path)

    # Load MCAP and measure memory
    tracemalloc.start()
    t0 = time.perf_counter()
    data_store = DataStore()
    data_store.load_mcap(mcap_path)
    load_time = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"MCAP load time:   {load_time:.3f}s")
    print(f"Memory \u2014 current: {current / 1e6:.1f} MB, peak: {peak / 1e6:.1f} MB")
    print(f"Joint samples:    {len(data_store.joint_timestamps)}")
    print(f"Image frames:     {len(data_store.images)}")
    print("=" * 50)

    app = QApplication(sys.argv)

    window = MainWindow(data_store)
    window.show()

    # Add default panels
    window.add_panel("3D Viewer")
    window.add_panel("Chart")
    window.add_panel("Image")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
