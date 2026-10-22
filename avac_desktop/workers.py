"""Explicit worker lifetime and main-thread result delivery."""
from __future__ import annotations

import threading
import traceback
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    result = Signal(object)
    failed = Signal(str)
    finished = Signal()
    progress = Signal(float)


class Worker(QRunnable):
    def __init__(self, function: Callable):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()
        self.cancelled = threading.Event()

    def run(self) -> None:
        try:
            result = self.function(self)
            if not self.cancelled.is_set():
                self.signals.result.emit(result)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Data task failed")
            self.signals.failed.emit(traceback.format_exc())
        finally:
            self.signals.finished.emit()


class Tasks(QObject):
    busy_changed = Signal(bool)
    interaction_busy_changed = Signal(bool)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        # Scientific legacy staging temporarily changes cwd; never allow two
        # preparation/conversion jobs to race within this process.
        self.pool.setMaxThreadCount(1)
        self.active: Worker | None = None

    def submit(self, function: Callable, result: Callable, *, passive=False) -> Worker:
        if self.active is not None:
            raise RuntimeError("Wait for the current data task to finish.")
        task = Worker(function)
        task.passive = passive
        self.active = task
        task.signals.result.connect(result)
        task.signals.failed.connect(self.error)
        task.signals.finished.connect(self._finished)
        self.busy_changed.emit(True)
        if not passive:
            self.interaction_busy_changed.emit(True)
        self.pool.start(task)
        return task

    def _finished(self) -> None:
        passive = self.active.passive
        self.active = None
        if not passive:
            self.interaction_busy_changed.emit(False)
        self.busy_changed.emit(False)

    def cancel(self) -> None:
        if self.active:
            self.active.cancelled.set()
