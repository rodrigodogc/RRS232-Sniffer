"""Formatação de bytes brutos para exibição (hexdump hex+ASCII)."""
from __future__ import annotations

from serial_sniffer.utils.time_utils import format_timestamp_ns


class HexAsciiFormatter:
    """Converte bytes em representações legíveis para a UI e exportação."""

    @staticmethod
    def to_hex(data: bytes, separator: str = " ") -> str:
        return separator.join(f"{b:02X}" for b in data)

    @staticmethod
    def to_ascii(data: bytes, placeholder: str = ".") -> str:
        return "".join(chr(b) if 32 <= b <= 126 else placeholder for b in data)

    @classmethod
    def format_row(cls, timestamp_ns: int, port_role: str, data: bytes) -> str:
        ts = format_timestamp_ns(timestamp_ns)
        hex_part = cls.to_hex(data)
        ascii_part = cls.to_ascii(data)
        return f"[{ts}] {port_role:>2} | {hex_part:<48} | {ascii_part}"

    @classmethod
    def format_hexdump_block(cls, data: bytes, bytes_per_line: int = 16) -> str:
        lines = []
        for offset in range(0, len(data), bytes_per_line):
            chunk = data[offset : offset + bytes_per_line]
            hex_part = cls.to_hex(chunk).ljust(bytes_per_line * 3 - 1)
            ascii_part = cls.to_ascii(chunk)
            lines.append(f"{offset:04X}  {hex_part}  {ascii_part}")
        return "\n".join(lines)
