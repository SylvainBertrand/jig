"""BackgroundExecutor — QThreadPool wrapper for offloading heavy work."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _WorkerSignals(QObject):
    finished = Signal(object)  # result
    error = Signal(Exception)


class _Worker(QRunnable):
    """Runs a callable on the thread pool and emits result/error."""

    def __init__(self, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.error.emit(exc)


class BackgroundExecutor:
    """Static utility for submitting work to a shared QThreadPool.

    Usage::

        BackgroundExecutor.submit(
            load_mcap, path,
            on_done=lambda result: print("loaded"),
            on_error=lambda exc: print(f"failed: {exc}"),
        )
    """

    _pool: QThreadPool | None = None

    @classmethod
    def pool(cls) -> QThreadPool:
        if cls._pool is None:
            cls._pool = QThreadPool()
            cls._pool.setMaxThreadCount(4)
        return cls._pool

    @classmethod
    def submit(
        cls,
        fn: Callable[..., Any],
        *args: Any,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        **kwargs: Any,
    ) -> _Worker:
        """Submit *fn* to run on a background thread.

        ``on_done`` and ``on_error`` are called on the **main thread**
        (via Qt signal/slot auto-connection).
        """
        worker = _Worker(fn, args, kwargs)
        if on_done is not None:
            worker.signals.finished.connect(on_done)
        if on_error is not None:
            worker.signals.error.connect(on_error)
        cls.pool().start(worker)
        return worker
