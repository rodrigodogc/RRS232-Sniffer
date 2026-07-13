"""Orquestra o ciclo de vida completo de uma sessão de captura ao vivo."""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import time

from serial_sniffer.capture.exceptions import CaptureAlreadyRunningError, PortOpenError
from serial_sniffer.capture.serial_reader import ReconnectPolicy, SerialPortReader
from serial_sniffer.config.settings import UI_QUEUE_MAX_SIZE
from serial_sniffer.models.enums import ConnectionStatus, PortRole
from serial_sniffer.models.session import CaptureConfig, Session
from serial_sniffer.parsing.frame_parser import FrameParser
from serial_sniffer.storage.db_writer_thread import DBWriterThread
from serial_sniffer.storage.framing_config_repository import FramingConfigRepository
from serial_sniffer.storage.packet_repository import PacketRepository
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository
from serial_sniffer.storage.session_repository import SessionRepository
from serial_sniffer.utils.time_utils import TimeAnchor

logger = logging.getLogger(__name__)


class CaptureSession:
    """Coordena os dois SerialPortReader (RX/TX), o DBWriterThread e o FrameParser
    ativo, do início ao fim de uma sessão de captura ao vivo."""

    def __init__(
        self,
        session_repository: SessionRepository,
        raw_chunk_repository: RawChunkRepository,
        packet_repository: PacketRepository,
        framing_config_repository: FramingConfigRepository,
        frame_parser: FrameParser,
    ):
        self.session_repository = session_repository
        self.raw_chunk_repository = raw_chunk_repository
        self.packet_repository = packet_repository
        self.framing_config_repository = framing_config_repository
        self.frame_parser = frame_parser

        self.session: Session | None = None
        self._capture_queue: "queue.Queue" = queue.Queue()
        self.ui_queue: "queue.Queue" = queue.Queue(maxsize=UI_QUEUE_MAX_SIZE)

        self._rx_reader: SerialPortReader | None = None
        self._tx_reader: SerialPortReader | None = None
        self._db_writer: DBWriterThread | None = None
        self._time_anchor: TimeAnchor | None = None
        self._running = False
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._running

    def start(self, config: CaptureConfig) -> Session:
        with self._lock:
            if self._running:
                raise CaptureAlreadyRunningError("Uma sessão de captura já está em execução")

            self._time_anchor = TimeAnchor.now()
            session = Session(
                id=None,
                name=config.session_name,
                created_at_ns=self._time_anchor.wallclock_ns,
                rx_port=config.rx_port,
                tx_port=config.tx_port,
                rx_baud=config.rx_baud,
                tx_baud=config.tx_baud,
                bytesize=config.bytesize,
                parity=config.parity,
                stopbits=config.stopbits,
            )
            session.id = self.session_repository.create(session)
            self.session = session

            self.frame_parser.reset()
            self._capture_queue = queue.Queue()
            self.ui_queue = queue.Queue(maxsize=UI_QUEUE_MAX_SIZE)

            self._db_writer = DBWriterThread(
                session_id=session.id,
                capture_queue=self._capture_queue,
                ui_queue=self.ui_queue,
                raw_chunk_repository=self.raw_chunk_repository,
            )

            seq_counter = itertools.count()
            seq_lock = threading.Lock()

            self._rx_reader = SerialPortReader(
                port_name=config.rx_port,
                baud=config.rx_baud,
                role=PortRole.RX,
                output_queue=self._capture_queue,
                seq_counter=seq_counter,
                seq_lock=seq_lock,
                time_anchor=self._time_anchor,
                bytesize=config.bytesize,
                parity=config.parity,
                stopbits=config.stopbits,
                reconnect_policy=ReconnectPolicy(),
            )
            self._tx_reader = SerialPortReader(
                port_name=config.tx_port,
                baud=config.tx_baud,
                role=PortRole.TX,
                output_queue=self._capture_queue,
                seq_counter=seq_counter,
                seq_lock=seq_lock,
                time_anchor=self._time_anchor,
                bytesize=config.bytesize,
                parity=config.parity,
                stopbits=config.stopbits,
                reconnect_policy=ReconnectPolicy(),
            )

            self._db_writer.start()
            self._rx_reader.start()
            self._tx_reader.start()

            # dá tempo das threads tentarem abrir as portas antes de reportar sucesso
            time.sleep(0.2)
            rx_status = self._rx_reader.status
            tx_status = self._tx_reader.status
            if rx_status == ConnectionStatus.ERROR and tx_status == ConnectionStatus.ERROR:
                rx_error = self._rx_reader.last_error or "erro desconhecido"
                tx_error = self._tx_reader.last_error or "erro desconhecido"
                self._teardown_threads()
                self.session_repository.delete(session.id)
                self.session = None
                raise PortOpenError(
                    f"Falha ao abrir ambas as portas.\nRX ({config.rx_port}): {rx_error}\n"
                    f"TX ({config.tx_port}): {tx_error}"
                )

            self._running = True
            return session

    def get_status_snapshot(self) -> dict:
        rx_status = self._rx_reader.status if self._rx_reader else ConnectionStatus.DISCONNECTED
        tx_status = self._tx_reader.status if self._tx_reader else ConnectionStatus.DISCONNECTED
        return {
            "rx_status": rx_status,
            "tx_status": tx_status,
            "total_chunks": self._db_writer.total_chunks if self._db_writer else 0,
            "total_bytes_rx": self._db_writer.total_bytes_rx if self._db_writer else 0,
            "total_bytes_tx": self._db_writer.total_bytes_tx if self._db_writer else 0,
            "queue_backlog": self._capture_queue.qsize(),
        }

    def tick_framing(self) -> list:
        """Chamado periodicamente pela UI para permitir que TimeoutFrameStrategy feche
        pacotes pendentes mesmo sem novos bytes chegando."""
        if not self._time_anchor:
            return []
        return self.frame_parser.tick(self._time_anchor.event_timestamp_ns())

    def stop(self) -> Session | None:
        with self._lock:
            if not self._running or not self.session:
                return self.session

            self._teardown_threads()

            pending_packets = self.frame_parser.flush_all()
            if pending_packets and self.session.default_framing_config_id:
                self.packet_repository.insert_batch(
                    self.session.id, self.session.default_framing_config_id, pending_packets
                )

            ended_at_ns = self._time_anchor.event_timestamp_ns() if self._time_anchor else 0
            snapshot = self.get_status_snapshot()
            self.session_repository.update_end(
                session_id=self.session.id,
                ended_at_ns=ended_at_ns,
                raw_chunk_count=snapshot["total_chunks"],
                total_bytes_rx=snapshot["total_bytes_rx"],
                total_bytes_tx=snapshot["total_bytes_tx"],
            )
            self.session = self.session_repository.get(self.session.id)
            self._running = False
            return self.session

    def _teardown_threads(self) -> None:
        if self._rx_reader:
            self._rx_reader.stop()
        if self._tx_reader:
            self._tx_reader.stop()
        if self._db_writer:
            self._db_writer.stop()

        if self._rx_reader:
            self._rx_reader.join(timeout=3)
        if self._tx_reader:
            self._tx_reader.join(timeout=3)
        if self._db_writer:
            self._db_writer.wait_flushed(timeout=5)
            self._db_writer.join(timeout=3)
