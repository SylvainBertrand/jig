"""LogSession — loads an MCAP log file on a background thread."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jig.core.background import BackgroundExecutor
from jig.core.session import Session
from jig.core.types import SessionType
from jig.io.mcap_reader import load_mcap_into


class LogSession(Session):
    """Session backed by an MCAP log file.

    Calls ``BackgroundExecutor.submit()`` so the GUI never blocks during load.
    Emits ``loading_finished`` when done.
    """

    def __init__(self, path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self._path = Path(path)
        self._metrics: dict[str, Any] = {}

    @property
    def session_type(self) -> SessionType:
        return SessionType.LOG

    @property
    def display_name(self) -> str:
        return self._path.name

    @property
    def path(self) -> Path:
        return self._path

    @property
    def metrics(self) -> dict[str, Any]:
        return self._metrics

    def start(self) -> None:
        """Begin loading the MCAP file on a background thread."""
        self.loading_started.emit()
        BackgroundExecutor.submit(
            load_mcap_into,
            self._data_store,
            self._path,
            on_done=self._on_load_done,
            on_error=self._on_load_error,
        )

    def _on_load_done(self, metrics: dict[str, Any]) -> None:
        self._metrics = metrics
        print(
            f"Loaded {self.display_name}: "
            f"{metrics['load_time_s']:.2f}s, "
            f"{metrics['memory_current_mb']:.1f} MB"
        )
        self.loading_finished.emit()

    def _on_load_error(self, exc: Exception) -> None:
        self.error_occurred.emit(str(exc))

    def stop(self) -> None:
        pass  # Log sessions are fully loaded; nothing to stop.
