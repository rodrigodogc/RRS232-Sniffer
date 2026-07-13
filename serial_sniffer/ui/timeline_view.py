"""Visualização em timeline única e cronológica, com cor por porta de origem."""
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


class TimelineView(ctk.CTkFrame):
    """Lista cronológica única (RX+TX intercalados) na ordem de chegada observada."""

    def __init__(self, master, on_select: Callable[[Packet], None], **kwargs):
        super().__init__(master, fg_color=theme.BG_PANEL, corner_radius=8, **kwargs)
        self.on_select = on_select
        self._packets: dict[str, Packet] = {}
        self._row_order: list[str] = []

        tree_frame = tk.Frame(self, bg=theme.BG_PANEL)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("ts", "port", "hex", "ascii"),
            show="headings",
            style="Sniffer.Treeview",
        )
        self.tree.heading("ts", text="Timestamp")
        self.tree.heading("port", text="Porta")
        self.tree.heading("hex", text="Hex")
        self.tree.heading("ascii", text="ASCII")
        self.tree.column("ts", width=120, anchor="w")
        self.tree.column("port", width=50, anchor="center")
        self.tree.column("hex", width=420, anchor="w")
        self.tree.column("ascii", width=180, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("rx", foreground=theme.RX_COLOR, background=theme.RX_ROW_BG)
        self.tree.tag_configure("tx", foreground=theme.TX_COLOR, background=theme.TX_ROW_BG)
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
        port_label = packet.port_role.value
        hex_str = HexAsciiFormatter.to_hex(packet.data)
        ascii_str = HexAsciiFormatter.to_ascii(packet.data)

        role_tag = "rx" if packet.port_role == PortRole.RX else "tx"
        tags = (role_tag, "highlight") if highlighted else (role_tag,)

        row_id = self.tree.insert(
            "", "end", values=(ts, port_label, hex_str, ascii_str), tags=tags
        )
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
