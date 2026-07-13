"""Thread única consumidora da fila de captura: grava em lote no SQLite e
repassa os mesmos eventos para a fila (bounded, descartável) que alimenta a UI.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from serial_sniffer.config.settings import DB_BATCH_INTERVAL_S, DB_BATCH_MAX_SIZE
from serial_sniffer.models.enums import PortRole
from serial_sniffer.models.packet import RawByteEvent
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository

logger = logging.getLogger(__name__)


class DBWriterThread(threading.Thread):
    """Drena `capture_queue`, grava em batch em `raw_chunks` e repassa para `ui_queue`."""

    def __init__(
        self,
        session_id: int,
        capture_queue: "queue.Queue[RawByteEvent]",
        ui_queue: "queue.Queue[RawByteEvent]",
        raw_chunk_repository: RawChunkRepository,
        batch_max_size: int = DB_BATCH_MAX_SIZE,
        batch_interval_s: float = DB_BATCH_INTERVAL_S,
    ):
        super().__init__(name="DBWriterThread", daemon=True)
        self.session_id = session_id
        self.capture_queue = capture_queue
        self.ui_queue = ui_queue
        self.raw_chunk_repository = raw_chunk_repository
        self.batch_max_size = batch_max_size
        self.batch_interval_s = batch_interval_s

        self._stop_event = threading.Event()
        self._flushed_event = threading.Event()
        self.total_chunks = 0
        self.total_bytes_rx = 0
        self.total_bytes_tx = 0

    def stop(self) -> None:
        self._stop_event.set()

    def wait_flushed(self, timeout: float = 5.0) -> bool:
        return self._flushed_event.wait(timeout)

    def run(self) -> None:
        batch: list[RawByteEvent] = []
        last_flush = time.monotonic()
        try:
            while True:
                timeout = max(0.0, self.batch_interval_s - (time.monotonic() - last_flush))
                try:
                    event = self.capture_queue.get(timeout=timeout or 0.01)
                    batch.append(event)
                except queue.Empty:
                    pass

                should_flush = (
                    len(batch) >= self.batch_max_size
                    or (time.monotonic() - last_flush) >= self.batch_interval_s
                )
                if should_flush and batch:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = time.monotonic()

                if self._stop_event.is_set() and self.capture_queue.empty() and not batch:
                    break
        except Exception:
            logger.exception("Erro fatal em DBWriterThread")
        finally:
            if batch:
                self._flush_batch(batch)
            self._flushed_event.set()

    def _flush_batch(self, batch: list[RawByteEvent]) -> None:
        try:
            self.raw_chunk_repository.insert_batch(self.session_id, batch)
        except Exception:
            logger.exception("Falha ao gravar lote de %d chunks no banco", len(batch))
            return

        self.total_chunks += len(batch)
        for event in batch:
            if event.port_role == PortRole.RX:
                self.total_bytes_rx += event.byte_count
            else:
                self.total_bytes_tx += event.byte_count
            try:
                self.ui_queue.put_nowait(event)
            except queue.Full:
                logger.warning("ui_queue cheia — descartando evento para manter a UI viva")
