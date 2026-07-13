"""Estruturas de dados de eventos brutos e pacotes derivados (framing)."""
from __future__ import annotations

from dataclasses import dataclass, field

from serial_sniffer.models.enums import PortRole


@dataclass(frozen=True)
class RawByteEvent:
    """Um chunk de bytes lido de uma porta serial em um único instante."""

    port_role: PortRole
    timestamp_ns: int
    seq: int
    data: bytes

    @property
    def byte_count(self) -> int:
        return len(self.data)


@dataclass
class Packet:
    """Um pacote derivado pela aplicação de uma estratégia de framing."""

    port_role: PortRole
    seq: int
    start_timestamp_ns: int
    end_timestamp_ns: int
    data: bytes
    framing_config_id: int | None = None
    session_id: int | None = None
    id: int | None = None
    checksums: dict[str, int] = field(default_factory=dict)
    last_byte_match_algo: str | None = None

    @property
    def byte_count(self) -> int:
        return len(self.data)
