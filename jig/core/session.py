"""Session ABC — represents a data source (log file, live connection, etc.)."""

from __future__ import annotations

from abc import abstractmethod

from PySide6.QtCore import QObject, Signal

from jig.core.data_store import DataStore
from jig.core.types import SessionType


class Session(QObject):
    """Base class for all data sessions.

    Signals:
        loading_started(): session began loading data.
        loading_progress(float): 0.0-1.0 progress fraction.
        loading_finished(): session finished loading data.
        error_occurred(str): an error message.
    """

    loading_started = Signal()
    loading_progress = Signal(float)
    loading_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._data_store = DataStore()

    @property
    @abstractmethod
    def session_type(self) -> SessionType:
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        ...

    @property
    def data_store(self) -> DataStore:
        return self._data_store

    @abstractmethod
    def start(self) -> None:
        """Begin loading or connecting. Must not block the main thread."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop loading or disconnect."""
        ...
