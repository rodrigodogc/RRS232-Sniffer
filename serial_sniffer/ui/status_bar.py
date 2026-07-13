"""Barra inferior de status: throughput, contagem de pacotes e backlog da fila."""
from __future__ import annotations

import customtkinter as ctk

from serial_sniffer.ui import theme


class StatusBar(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=theme.BG_PANEL, corner_radius=8, **kwargs)

        self.info_label = ctk.CTkLabel(self, text="Pronto.", font=theme.FONT_UI, anchor="w")
        self.info_label.pack(side="left", padx=10, pady=4)

        self.backlog_label = ctk.CTkLabel(self, text="", font=theme.FONT_UI, anchor="e")
        self.backlog_label.pack(side="right", padx=10, pady=4)

        self._last_bytes_rx = 0
        self._last_bytes_tx = 0
        self._last_time: float | None = None

    def update_snapshot(self, snapshot: dict) -> None:
        total_rx = snapshot.get("total_bytes_rx", 0)
        total_tx = snapshot.get("total_bytes_tx", 0)
        chunks = snapshot.get("total_chunks", 0)
        backlog = snapshot.get("queue_backlog", 0)

        self.info_label.configure(
            text=(
                f"RX: {total_rx:,} bytes  |  TX: {total_tx:,} bytes  |  "
                f"Chunks gravados: {chunks:,}"
            )
        )
        if backlog > 500:
            self.backlog_label.configure(
                text=f"Backlog da fila: {backlog}", text_color=theme.STATUS_ERROR
            )
        else:
            self.backlog_label.configure(text="", text_color=theme.FG_MUTED)

    def set_message(self, message: str, is_error: bool = False) -> None:
        self.info_label.configure(
            text=message, text_color=theme.STATUS_ERROR if is_error else theme.FG_TEXT
        )
