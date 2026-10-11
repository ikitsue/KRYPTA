"""Exécution asynchrone des traitements dans le pool Qt."""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    succeeded = Signal(str)
    failed = Signal(str)


class TransformWorker(QRunnable):
    def __init__(self, operation: Callable[[], str]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.operation()
        except (ValueError, OSError) as error:
            logger.warning("Traitement échoué (%s).", type(error).__name__)
            self.signals.failed.emit(str(error))
            return
        self.signals.succeeded.emit(result)
