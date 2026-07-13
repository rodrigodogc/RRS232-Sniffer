"""Exportação de sessões capturadas para CSV ou hexdump em texto puro."""
from __future__ import annotations

import csv
from pathlib import Path

from serial_sniffer.parsing.formatter import HexAsciiFormatter
from serial_sniffer.storage.packet_repository import PacketRepository
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository
from serial_sniffer.utils.time_utils import format_timestamp_ns


class SessionExporter:
    """Exporta os `raw_chunks` de uma sessão, ou os `packets` de uma config de framing."""

    def __init__(
        self,
        raw_chunk_repository: RawChunkRepository,
        packet_repository: PacketRepository,
    ):
        self.raw_chunk_repository = raw_chunk_repository
        self.packet_repository = packet_repository

    def export_csv(
        self,
        session_id: int,
        dest_path: Path,
        source: str = "raw",
        framing_config_id: int | None = None,
    ) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["seq", "port_role", "timestamp", "byte_count", "hex", "ascii"])
            if source == "raw":
                for event in self.raw_chunk_repository.stream_session(session_id):
                    writer.writerow([
                        event.seq,
                        event.port_role.value,
                        format_timestamp_ns(event.timestamp_ns),
                        event.byte_count,
                        HexAsciiFormatter.to_hex(event.data),
                        HexAsciiFormatter.to_ascii(event.data),
                    ])
            else:
                if framing_config_id is None:
                    raise ValueError("framing_config_id é obrigatório para source='packets'")
                for packet in self.packet_repository.list_for_session(
                    session_id, framing_config_id
                ):
                    writer.writerow([
                        packet.seq,
                        packet.port_role.value,
                        format_timestamp_ns(packet.start_timestamp_ns),
                        packet.byte_count,
                        HexAsciiFormatter.to_hex(packet.data),
                        HexAsciiFormatter.to_ascii(packet.data),
                    ])
        return dest_path

    def export_hexdump_txt(
        self,
        session_id: int,
        dest_path: Path,
        source: str = "raw",
        framing_config_id: int | None = None,
    ) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            if source == "raw":
                for event in self.raw_chunk_repository.stream_session(session_id):
                    f.write(HexAsciiFormatter.format_row(
                        event.timestamp_ns, event.port_role.value, event.data
                    ))
                    f.write("\n")
            else:
                if framing_config_id is None:
                    raise ValueError("framing_config_id é obrigatório para source='packets'")
                for packet in self.packet_repository.list_for_session(
                    session_id, framing_config_id
                ):
                    f.write(f"--- pacote seq={packet.seq} porta={packet.port_role.value} "
                            f"ts={format_timestamp_ns(packet.start_timestamp_ns)} ---\n")
                    f.write(HexAsciiFormatter.format_hexdump_block(packet.data))
                    f.write("\n\n")
        return dest_path
