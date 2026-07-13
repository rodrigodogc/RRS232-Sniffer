"""Estratégias de framing (Strategy pattern) e o contexto que as aplica por porta.

Os bytes brutos gravados no banco nunca dependem de framing. FrameStrategy é
uma lente de análise aplicada em memória sobre RawByteEvents (ao vivo ou ao
reprocessar uma sessão histórica), produzindo Packets.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from serial_sniffer.config.settings import DELIMITER_MAX_BUFFER_SIZE
from serial_sniffer.models.enums import FramingMode, PortRole
from serial_sniffer.models.packet import Packet, RawByteEvent


class FrameStrategy(ABC):
    """Interface de uma estratégia de agrupamento de bytes em pacotes."""

    @abstractmethod
    def feed(self, event: RawByteEvent) -> list[Packet]:
        """Consome um evento de bytes brutos, retorna 0+ pacotes completos."""

    @abstractmethod
    def tick(self, now_ns: int) -> list[Packet]:
        """Chamado periodicamente mesmo sem novos bytes (necessário p/ timeout)."""

    @abstractmethod
    def flush(self) -> Packet | None:
        """Fecha e retorna um pacote pendente (usado ao parar a sessão)."""

    @abstractmethod
    def reset(self) -> None:
        """Descarta qualquer estado/buffer pendente."""


class NoFramingStrategy(FrameStrategy):
    """Passthrough: cada chunk lido da serial já é considerado um "pacote"."""

    def feed(self, event: RawByteEvent) -> list[Packet]:
        if not event.data:
            return []
        packet = Packet(
            port_role=event.port_role,
            seq=event.seq,
            start_timestamp_ns=event.timestamp_ns,
            end_timestamp_ns=event.timestamp_ns,
            data=event.data,
        )
        return [packet]

    def tick(self, now_ns: int) -> list[Packet]:
        return []

    def flush(self) -> Packet | None:
        return None

    def reset(self) -> None:
        pass


class DelimiterFrameStrategy(FrameStrategy):
    """Agrupa bytes entre um delimitador de início e um de fim (ex: STX/ETX).

    Sem escape_byte, qualquer ocorrência de start_bytes/end_bytes DENTRO do
    payload (coincidência de valor, comum em dados binários não protegidos)
    fecha/abre pacotes prematuramente. Se o protocolo do fabricante usa
    byte-stuffing (um byte de escape precede toda ocorrência literal de STX,
    ETX ou do próprio escape dentro do payload), configure escape_byte para
    que esses bytes literais sejam repassados sem interpretação — o parser
    remove o escape e mantém o byte original no pacote reconstruído.
    """

    def __init__(
        self,
        start_bytes: bytes | None,
        end_bytes: bytes,
        include_delimiters: bool = False,
        max_buffer_size: int = DELIMITER_MAX_BUFFER_SIZE,
        escape_byte: bytes | None = None,
    ):
        if not end_bytes:
            raise ValueError("end_bytes é obrigatório para DelimiterFrameStrategy")
        self.start_bytes = start_bytes or b""
        self.end_bytes = end_bytes
        self.include_delimiters = include_delimiters
        self.max_buffer_size = max_buffer_size
        self.escape_byte = escape_byte or b""
        self._buffer = bytearray()
        self._buffer_start_ts: int | None = None
        self._buffer_seq: int | None = None
        self._armed = not bool(self.start_bytes)
        self._escape_active = False
        self._port_role: PortRole | None = None

    def feed(self, event: RawByteEvent) -> list[Packet]:
        self._port_role = event.port_role
        packets: list[Packet] = []
        for b in event.data:
            if self._buffer_start_ts is None:
                self._buffer_start_ts = event.timestamp_ns
                self._buffer_seq = event.seq

            if not self._armed:
                # fora de um pacote: escape não se aplica, apenas procura o
                # delimitador de início literal
                self._buffer.append(b)
                if self._buffer.endswith(self.start_bytes):
                    # descarta sempre o lixo acumulado antes do delimitador de
                    # início; include_delimiters só decide se o próprio
                    # start_bytes permanece no pacote final
                    if self.include_delimiters:
                        del self._buffer[: len(self._buffer) - len(self.start_bytes)]
                    else:
                        del self._buffer[:]
                    self._armed = True
                    self._escape_active = False
                    self._buffer_start_ts = event.timestamp_ns
                continue

            if self._escape_active:
                # byte literal protegido por byte-stuffing: nunca interpretado
                # como delimitador, mesmo que coincida com start/end_bytes
                self._escape_active = False
                self._buffer.append(b)
                continue

            if self.escape_byte and bytes([b]) == self.escape_byte:
                self._escape_active = True
                continue

            self._buffer.append(b)
            if self._buffer.endswith(self.end_bytes):
                data = bytes(self._buffer)
                if not self.include_delimiters:
                    data = data[: -len(self.end_bytes)]
                packets.append(
                    Packet(
                        port_role=event.port_role,
                        seq=self._buffer_seq or event.seq,
                        start_timestamp_ns=self._buffer_start_ts,
                        end_timestamp_ns=event.timestamp_ns,
                        data=data,
                    )
                )
                self._buffer.clear()
                self._buffer_start_ts = None
                self._armed = not bool(self.start_bytes)
            elif len(self._buffer) >= self.max_buffer_size:
                # guarda de segurança: delimitador de fim nunca chegou
                self._buffer.clear()
                self._buffer_start_ts = None
                self._armed = not bool(self.start_bytes)
        return packets

    def tick(self, now_ns: int) -> list[Packet]:
        return []

    def flush(self) -> Packet | None:
        if not self._buffer or self._buffer_start_ts is None or self._port_role is None:
            return None
        packet = Packet(
            port_role=self._port_role,
            seq=self._buffer_seq or 0,
            start_timestamp_ns=self._buffer_start_ts,
            end_timestamp_ns=self._buffer_start_ts,
            data=bytes(self._buffer),
        )
        self.reset()
        return packet

    def reset(self) -> None:
        self._buffer.clear()
        self._buffer_start_ts = None
        self._buffer_seq = None
        self._armed = not bool(self.start_bytes)
        self._escape_active = False


class TimeoutFrameStrategy(FrameStrategy):
    """Fecha um pacote quando o silêncio entre bytes excede um timeout."""

    def __init__(self, inter_byte_timeout_ms: int):
        if inter_byte_timeout_ms <= 0:
            raise ValueError("inter_byte_timeout_ms deve ser positivo")
        self.timeout_ns = inter_byte_timeout_ms * 1_000_000
        self._buffer = bytearray()
        self._buffer_start_ts: int | None = None
        self._buffer_seq: int | None = None
        self._last_byte_ts: int | None = None
        self._port_role: PortRole | None = None

    def feed(self, event: RawByteEvent) -> list[Packet]:
        packets: list[Packet] = []
        if (
            self._last_byte_ts is not None
            and event.timestamp_ns - self._last_byte_ts > self.timeout_ns
        ):
            closed = self.flush()
            if closed:
                packets.append(closed)

        if not event.data:
            return packets

        self._port_role = event.port_role
        if self._buffer_start_ts is None:
            self._buffer_start_ts = event.timestamp_ns
            self._buffer_seq = event.seq
        self._buffer.extend(event.data)
        self._last_byte_ts = event.timestamp_ns
        return packets

    def tick(self, now_ns: int) -> list[Packet]:
        if (
            self._last_byte_ts is not None
            and now_ns - self._last_byte_ts > self.timeout_ns
        ):
            closed = self.flush()
            return [closed] if closed else []
        return []

    def flush(self) -> Packet | None:
        if not self._buffer or self._buffer_start_ts is None or self._port_role is None:
            self.reset()
            return None
        packet = Packet(
            port_role=self._port_role,
            seq=self._buffer_seq or 0,
            start_timestamp_ns=self._buffer_start_ts,
            end_timestamp_ns=self._last_byte_ts or self._buffer_start_ts,
            data=bytes(self._buffer),
        )
        self.reset()
        return packet

    def reset(self) -> None:
        self._buffer.clear()
        self._buffer_start_ts = None
        self._buffer_seq = None
        self._last_byte_ts = None


class FixedLengthFrameStrategy(FrameStrategy):
    """Fecha um pacote a cada N bytes acumulados."""

    def __init__(self, length: int):
        if length <= 0:
            raise ValueError("length deve ser positivo")
        self.length = length
        self._buffer = bytearray()
        self._buffer_start_ts: int | None = None
        self._buffer_seq: int | None = None
        self._last_ts: int | None = None
        self._port_role: PortRole | None = None

    def feed(self, event: RawByteEvent) -> list[Packet]:
        packets: list[Packet] = []
        self._port_role = event.port_role
        for b in event.data:
            if self._buffer_start_ts is None:
                self._buffer_start_ts = event.timestamp_ns
                self._buffer_seq = event.seq
            self._buffer.append(b)
            self._last_ts = event.timestamp_ns
            if len(self._buffer) >= self.length:
                packets.append(
                    Packet(
                        port_role=event.port_role,
                        seq=self._buffer_seq or event.seq,
                        start_timestamp_ns=self._buffer_start_ts,
                        end_timestamp_ns=event.timestamp_ns,
                        data=bytes(self._buffer),
                    )
                )
                self._buffer.clear()
                self._buffer_start_ts = None
        return packets

    def tick(self, now_ns: int) -> list[Packet]:
        return []

    def flush(self) -> Packet | None:
        if not self._buffer or self._buffer_start_ts is None or self._port_role is None:
            return None
        packet = Packet(
            port_role=self._port_role,
            seq=self._buffer_seq or 0,
            start_timestamp_ns=self._buffer_start_ts,
            end_timestamp_ns=self._last_ts or self._buffer_start_ts,
            data=bytes(self._buffer),
        )
        self.reset()
        return packet

    def reset(self) -> None:
        self._buffer.clear()
        self._buffer_start_ts = None
        self._buffer_seq = None
        self._last_ts = None


def build_strategy(
    mode: FramingMode,
    start_bytes: bytes | None = None,
    end_bytes: bytes | None = None,
    include_delimiters: bool = False,
    inter_byte_timeout_ms: int | None = None,
    fixed_length: int | None = None,
    escape_byte: bytes | None = None,
) -> FrameStrategy:
    if mode == FramingMode.NONE:
        return NoFramingStrategy()
    if mode == FramingMode.DELIMITER:
        return DelimiterFrameStrategy(
            start_bytes, end_bytes or b"", include_delimiters, escape_byte=escape_byte
        )
    if mode == FramingMode.TIMEOUT:
        return TimeoutFrameStrategy(inter_byte_timeout_ms or 20)
    if mode == FramingMode.FIXED_LENGTH:
        return FixedLengthFrameStrategy(fixed_length or 8)
    raise ValueError(f"Modo de framing desconhecido: {mode}")


class FrameParser:
    """Contexto Strategy: mantém uma FrameStrategy independente por porta (RX/TX)."""

    def __init__(self, mode: FramingMode = FramingMode.NONE, **strategy_kwargs):
        self._mode = mode
        self._strategy_kwargs = strategy_kwargs
        self._strategies: dict[PortRole, FrameStrategy] = {
            PortRole.RX: build_strategy(mode, **strategy_kwargs),
            PortRole.TX: build_strategy(mode, **strategy_kwargs),
        }

    def set_strategy(self, mode: FramingMode, **strategy_kwargs) -> None:
        self._mode = mode
        self._strategy_kwargs = strategy_kwargs
        self._strategies = {
            PortRole.RX: build_strategy(mode, **strategy_kwargs),
            PortRole.TX: build_strategy(mode, **strategy_kwargs),
        }

    @property
    def mode(self) -> FramingMode:
        return self._mode

    def feed(self, event: RawByteEvent) -> list[Packet]:
        return self._strategies[event.port_role].feed(event)

    def tick(self, now_ns: int) -> list[Packet]:
        packets: list[Packet] = []
        for strategy in self._strategies.values():
            packets.extend(strategy.tick(now_ns))
        return packets

    def flush_all(self) -> list[Packet]:
        packets = []
        for strategy in self._strategies.values():
            p = strategy.flush()
            if p:
                packets.append(p)
        return packets

    def reset(self) -> None:
        for strategy in self._strategies.values():
            strategy.reset()
