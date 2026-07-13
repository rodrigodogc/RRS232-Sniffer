"""Thread de leitura passiva de uma porta serial (RX-only, nunca escreve)."""
from __future__ import annotations

import itertools
import logging
import queue
import threading
from dataclasses import dataclass

import serial
from serial import SerialException

from serial_sniffer.capture.exceptions import PortBusyError, PortOpenError
from serial_sniffer.config.settings import (
    RECONNECT_RETRY_INTERVAL_S,
    SERIAL_MAX_CHUNK_SIZE,
    SERIAL_READ_TIMEOUT_S,
)
from serial_sniffer.models.enums import ConnectionStatus, PortRole
from serial_sniffer.models.packet import RawByteEvent
from serial_sniffer.utils.time_utils import TimeAnchor

logger = logging.getLogger(__name__)


@dataclass
class ReconnectPolicy:
    """Política de reconexão automática após desconexão da porta.

    Limitação conhecida: se o adaptador USB for religado em outra entrada
    física, o Windows pode atribuir um novo nome de COM — a reconexão
    automática só funciona religando na mesma porta; caso contrário, é
    necessário reselecionar a porta manualmente na UI.
    """

    retry_interval_s: float = RECONNECT_RETRY_INTERVAL_S
    max_retries: int | None = None


class SerialPortReader(threading.Thread):
    """Lê continuamente uma porta COM em modo somente-leitura e publica chunks
    numa fila compartilhada. Uma instância por porta (RX e TX são independentes)."""

    def __init__(
        self,
        port_name: str,
        baud: int,
        role: PortRole,
        output_queue: "queue.Queue",
        seq_counter: itertools.count,
        seq_lock: threading.Lock,
        time_anchor: TimeAnchor,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        reconnect_policy: ReconnectPolicy | None = None,
        status_callback=None,
    ):
        super().__init__(name=f"SerialReader-{role.value}", daemon=True)
        self.port_name = port_name
        self.baud = baud
        self.role = role
        self.output_queue = output_queue
        self._seq_counter = seq_counter
        self._seq_lock = seq_lock
        self.time_anchor = time_anchor
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.reconnect_policy = reconnect_policy or ReconnectPolicy()
        self.status_callback = status_callback

        self._stop_event = threading.Event()
        self._status = ConnectionStatus.DISCONNECTED
        self._status_lock = threading.Lock()
        self._serial: serial.Serial | None = None
        self.last_error: str | None = None

    @property
    def status(self) -> ConnectionStatus:
        with self._status_lock:
            return self._status

    def _set_status(self, status: ConnectionStatus) -> None:
        with self._status_lock:
            self._status = status
        if self.status_callback:
            try:
                self.status_callback(self.role, status)
            except Exception:
                logger.exception("Erro no status_callback de %s", self.role)

    def _next_seq(self) -> int:
        with self._seq_lock:
            return next(self._seq_counter)

    def _open_port(self) -> serial.Serial:
        self._set_status(ConnectionStatus.CONNECTING)
        try:
            return serial.Serial(
                port=self.port_name,
                baudrate=self.baud,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=SERIAL_READ_TIMEOUT_S,
            )
        except SerialException as exc:
            self._set_status(ConnectionStatus.ERROR)
            message = str(exc).lower()
            # PermissionError(13, ...) e "errno 13" são independentes do idioma do SO;
            # "access is denied"/"busy"/"in use" cobrem variações em inglês.
            busy_markers = (
                "access is denied", "busy", "in use",
                "permissionerror(13", "errno 13",
            )
            if any(marker in message for marker in busy_markers):
                raise PortBusyError(f"Porta {self.port_name} está ocupada: {exc}") from exc
            raise PortOpenError(f"Falha ao abrir {self.port_name}: {exc}") from exc

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._serial = self._open_port()
        except PortOpenError as exc:
            self.last_error = str(exc)
            logger.error("Falha ao abrir %s: %s", self.port_name, exc)
            return
        self._set_status(ConnectionStatus.CONNECTED)

        retries = 0
        while not self._stop_event.is_set():
            try:
                waiting = self._serial.in_waiting
                size = min(max(waiting, 1), SERIAL_MAX_CHUNK_SIZE)
                data = self._serial.read(size)
                if data:
                    event = RawByteEvent(
                        port_role=self.role,
                        timestamp_ns=self.time_anchor.event_timestamp_ns(),
                        seq=self._next_seq(),
                        data=data,
                    )
                    self.output_queue.put(event)
            except SerialException:
                logger.warning("Porta %s desconectada, tentando reconectar...", self.port_name)
                self._set_status(ConnectionStatus.DISCONNECTED)
                self._close_serial()
                if not self._try_reconnect(retries):
                    break
                retries += 1
                continue
            except Exception:
                logger.exception("Erro inesperado lendo %s", self.port_name)
                self._set_status(ConnectionStatus.ERROR)
                break

        self._close_serial()
        if self._status != ConnectionStatus.ERROR:
            self._set_status(ConnectionStatus.DISCONNECTED)

    def _try_reconnect(self, retries: int) -> bool:
        policy = self.reconnect_policy
        if policy.max_retries is not None and retries >= policy.max_retries:
            self._set_status(ConnectionStatus.ERROR)
            return False
        if self._stop_event.wait(policy.retry_interval_s):
            return False
        try:
            self._serial = self._open_port()
            self._set_status(ConnectionStatus.CONNECTED)
            return True
        except PortOpenError:
            return True  # continua tentando no próximo loop

    def _close_serial(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
