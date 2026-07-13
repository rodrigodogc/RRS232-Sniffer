"""Visualização em duas colunas: RX à esquerda, TX à direita."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

import customtkinter as ctk

from serial_sniffer.config.settings import UI_MAX_VISIBLE_ROWS
from serial_sniffer.models.enums import PortRole
from serial_sniffer.models.packet import Packet
from serial_sniffer.parsing.formatter import HexAsciiFormatter
from serial_sniffer.ui import theme
from serial_sniffer.utils.time_utils import format_timestamp_ns


class _PacketColumn(ctk.CTkFrame):
    def __init__(self, master, title: str, accent: str, on_select: Callable[[Packet], None]):
        super().__init__(master, fg_color=theme.BG_PANEL, corner_radius=8)
        self.on_select = on_select
        self._packets: dict[str, Packet] = {}
        self._row_order: list[str] = []

        ctk.CTkLabel(
            self, text=title, font=theme.FONT_UI_BOLD, text_color=accent
        ).pack(anchor="w", padx=10, pady=(6, 0))

        tree_frame = tk.Frame(self, bg=theme.BG_PANEL)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("ts", "hex", "ascii"),
            show="headings",
            style="Sniffer.Treeview",
        )
        self.tree.heading("ts", text="Timestamp")
        self.tree.heading("hex", text="Hex")
        self.tree.heading("ascii", text="ASCII")
        self.tree.column("ts", width=110, anchor="w")
        self.tree.column("hex", width=320, anchor="w")
        self.tree.column("ascii", width=140, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("highlight", background=theme.HIGHLIGHT_BG)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _on_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        packet = self._packets.get(selection[0])
        if packet:
            self.on_select(packet)

    def add_packet(self, packet: Packet, highlighted: bool = False) -> None:
        ts = format_timestamp_ns(packet.start_timestamp_ns)
        hex_str = HexAsciiFormatter.to_hex(packet.data)
        ascii_str = HexAsciiFormatter.to_ascii(packet.data)
        tags = ("highlight",) if highlighted else ()
        row_id = self.tree.insert("", "end", values=(ts, hex_str, ascii_str), tags=tags)
        self._packets[row_id] = packet
        self._row_order.append(row_id)

        autoscroll = not self.tree.selection()
        if autoscroll:
            self.tree.see(row_id)

        while len(self._row_order) > UI_MAX_VISIBLE_ROWS:
            old_id = self._row_order.pop(0)
            self._packets.pop(old_id, None)
            if self.tree.exists(old_id):
                self.tree.delete(old_id)

    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._packets.clear()
        self._row_order.clear()


class TwoColumnView(ctk.CTkFrame):
    """RX à esquerda, TX à direita — cada porta com seu próprio buffer/scroll."""

    def __init__(self, master, on_select: Callable[[Packet], None], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.rx_column = _PacketColumn(self, "RX", theme.RX_COLOR, on_select)
        self.rx_column.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.tx_column = _PacketColumn(self, "TX", theme.TX_COLOR, on_select)
        self.tx_column.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

    def add_packet(self, packet: Packet, highlighted: bool = False) -> None:
        column = self.rx_column if packet.port_role == PortRole.RX else self.tx_column
        column.add_packet(packet, highlighted)

    def clear(self) -> None:
        self.rx_column.clear()
        self.tx_column.clear()
