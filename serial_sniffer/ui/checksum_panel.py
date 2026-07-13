"""Painel de checksums do pacote selecionado, com verificação do último byte."""
from __future__ import annotations

import customtkinter as ctk

from serial_sniffer.models.enums import ChecksumAlgorithm
from serial_sniffer.models.packet import Packet
from serial_sniffer.parsing.checksum import ChecksumCalculator
from serial_sniffer.parsing.formatter import HexAsciiFormatter
from serial_sniffer.ui import theme

_VERIFIABLE_ALGORITHMS = [
    ChecksumAlgorithm.XOR,
    ChecksumAlgorithm.SUM8,
    ChecksumAlgorithm.CRC8,
]


class ChecksumPanel(ctk.CTkFrame):
    """Mostra os checksums calculados sobre o pacote selecionado em qualquer view."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PANEL, corner_radius=8, **kwargs)

        self.title_label = ctk.CTkLabel(
            self, text="Selecione um pacote para ver detalhes", font=theme.FONT_UI_BOLD
        )
        self.title_label.pack(anchor="w", padx=10, pady=(6, 2))

        self.values_label = ctk.CTkLabel(
            self, text="", font=theme.FONT_MONO, justify="left", anchor="w"
        )
        self.values_label.pack(anchor="w", padx=10, pady=(0, 2))

        self.match_label = ctk.CTkLabel(
            self, text="", font=theme.FONT_UI, justify="left", anchor="w"
        )
        self.match_label.pack(anchor="w", padx=10, pady=(0, 6))

    def show_packet(self, packet: Packet) -> None:
        data = packet.data
        self.title_label.configure(
            text=f"Pacote {packet.port_role.value}  |  {packet.byte_count} bytes  |  "
            f"{HexAsciiFormatter.to_hex(data)}"
        )

        if not data:
            self.values_label.configure(text="")
            self.match_label.configure(text="")
            return

        checksums = ChecksumCalculator.compute_all(data)
        values_text = "   ".join(f"{name}: 0x{val:04X}" for name, val in checksums.items())
        self.values_label.configure(text=values_text)

        matches = []
        for algo in _VERIFIABLE_ALGORITHMS:
            ok, expected, actual = ChecksumCalculator.verify_last_byte(data, algo)
            symbol = "✓" if ok else "✗"
            color = theme.MATCH_OK if ok else theme.MATCH_FAIL
            matches.append((f"{algo.value} {symbol} (esperado 0x{expected:02X}, "
                             f"último byte 0x{actual:02X})", color))

        best_match = next((m for m in matches if m[1] == theme.MATCH_OK), matches[0])
        self.match_label.configure(
            text="Verificação do último byte: " + " | ".join(m[0] for m in matches),
            text_color=best_match[1] if any(m[1] == theme.MATCH_OK for m in matches) else theme.FG_MUTED,
        )

    def clear(self) -> None:
        self.title_label.configure(text="Selecione um pacote para ver detalhes")
        self.values_label.configure(text="")
        self.match_label.configure(text="")
