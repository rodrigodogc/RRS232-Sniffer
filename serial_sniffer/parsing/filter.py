"""Filtro/busca por sequência de bytes, aplicado em memória sobre dados já lidos."""
from __future__ import annotations


class ByteSequenceFilter:
    """Busca uma sequência de bytes (informada em hex ou texto) dentro de `data`."""

    def __init__(self, pattern: str, is_hex: bool = True):
        self.pattern_str = pattern
        self.is_hex = is_hex
        self.pattern_bytes = self._parse_pattern(pattern, is_hex)

    @staticmethod
    def _parse_pattern(pattern: str, is_hex: bool) -> bytes:
        if not pattern:
            return b""
        if is_hex:
            cleaned = pattern.replace(" ", "").replace("0x", "").replace(",", "")
            if len(cleaned) % 2 != 0:
                cleaned = "0" + cleaned
            try:
                return bytes.fromhex(cleaned)
            except ValueError:
                return b""
        return pattern.encode("latin-1", errors="ignore")

    @property
    def is_empty(self) -> bool:
        return len(self.pattern_bytes) == 0

    def matches(self, data: bytes) -> bool:
        if self.is_empty:
            return True
        return self.pattern_bytes in data

    def highlight_positions(self, data: bytes) -> list[tuple[int, int]]:
        """Retorna lista de (start, end) exclusivo de todas as ocorrências."""
        if self.is_empty:
            return []
        positions = []
        start = 0
        plen = len(self.pattern_bytes)
        while True:
            idx = data.find(self.pattern_bytes, start)
            if idx == -1:
                break
            positions.append((idx, idx + plen))
            start = idx + plen
        return positions
