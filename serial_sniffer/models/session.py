"""Estruturas de dados de sessão de captura e configuração de framing."""
from __future__ import annotations

from dataclasses import dataclass

from serial_sniffer.models.enums import FramingMode


@dataclass
class CaptureConfig:
    """Parâmetros escolhidos pelo usuário na barra superior antes de iniciar."""

    session_name: str
    rx_port: str
    rx_baud: int
    tx_port: str
    tx_baud: int
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    db_path: str = ""


@dataclass
class Session:
    """Espelha a tabela `sessions`."""

    id: int | None
    name: str
    created_at_ns: int
    rx_port: str
    tx_port: str
    rx_baud: int
    tx_baud: int
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    ended_at_ns: int | None = None
    raw_chunk_count: int = 0
    total_bytes_rx: int = 0
    total_bytes_tx: int = 0
    default_framing_config_id: int | None = None
    notes: str | None = None

    @property
    def is_running(self) -> bool:
        return self.ended_at_ns is None


@dataclass
class FrameConfigDTO:
    """Espelha a tabela `framing_configs`."""

    mode: FramingMode
    id: int | None = None
    name: str | None = None
    start_bytes: bytes | None = None
    end_bytes: bytes | None = None
    include_delimiters: bool = False
    inter_byte_timeout_ms: int | None = None
    fixed_length: int | None = None
    escape_byte: bytes | None = None
    created_at_ns: int | None = None
