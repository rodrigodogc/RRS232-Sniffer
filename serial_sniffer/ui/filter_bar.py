"""Campo de busca/filtro por sequência de bytes, com destaque em tempo real."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from serial_sniffer.parsing.filter import ByteSequenceFilter
from serial_sniffer.ui import theme


class FilterBar(ctk.CTkFrame):
    def __init__(self, master, on_change: Callable[[ByteSequenceFilter], None], **kwargs):
        super().__init__(master, fg_color=theme.BG_PANEL, corner_radius=8, **kwargs)
        self.on_change = on_change

        ctk.CTkLabel(self, text="Filtro:", font=theme.FONT_UI).pack(
            side="left", padx=(10, 4), pady=6
        )
        self.pattern_entry = ctk.CTkEntry(
            self, width=220, placeholder_text="ex: A5 5A ou texto"
        )
        self.pattern_entry.pack(side="left", padx=4, pady=6)
        self.pattern_entry.bind("<KeyRelease>", lambda _e: self._notify())

        self.mode_switch = ctk.CTkSegmentedButton(
            self, values=["Hex", "Texto"], command=lambda _v: self._notify()
        )
        self.mode_switch.set("Hex")
        self.mode_switch.pack(side="left", padx=6, pady=6)

        self.clear_button = ctk.CTkButton(
            self, text="Limpar", width=70, command=self._clear
        )
        self.clear_button.pack(side="left", padx=6, pady=6)

    def _clear(self) -> None:
        self.pattern_entry.delete(0, "end")
        self._notify()

    def _notify(self) -> None:
        pattern = self.pattern_entry.get().strip()
        is_hex = self.mode_switch.get() == "Hex"
        self.on_change(ByteSequenceFilter(pattern, is_hex=is_hex))

    def current_filter(self) -> ByteSequenceFilter:
        pattern = self.pattern_entry.get().strip()
        is_hex = self.mode_switch.get() == "Hex"
        return ByteSequenceFilter(pattern, is_hex=is_hex)
