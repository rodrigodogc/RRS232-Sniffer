"""Janela de revisão: lista sessões salvas e permite reabri-las com framing distinto."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import customtkinter as ctk

from serial_sniffer.config.settings import EXPORT_DIR
from serial_sniffer.models.enums import FramingMode
from serial_sniffer.models.packet import RawByteEvent
from serial_sniffer.models.session import FrameConfigDTO
from serial_sniffer.parsing.frame_parser import FrameParser
from serial_sniffer.storage.exporter import SessionExporter
from serial_sniffer.storage.framing_config_repository import FramingConfigRepository
from serial_sniffer.storage.packet_repository import PacketRepository
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository
from serial_sniffer.storage.session_repository import SessionRepository
from serial_sniffer.ui import theme
from serial_sniffer.ui.framing_config_dialog import FramingConfigDialog
from serial_sniffer.ui.timeline_view import TimelineView
from serial_sniffer.ui.two_column_view import TwoColumnView
from serial_sniffer.utils.time_utils import format_timestamp_ns


class SessionBrowserWindow(ctk.CTkToplevel):
    """Lista sessões históricas e reabre uma delas em modo revisão (somente leitura)."""

    def __init__(
        self,
        master,
        session_repository: SessionRepository,
        raw_chunk_repository: RawChunkRepository,
        packet_repository: PacketRepository,
        framing_config_repository: FramingConfigRepository,
        exporter: SessionExporter,
    ):
        super().__init__(master)
        self.title("Sessões salvas — Revisão")
        self.geometry("1100x650")
        self.configure(fg_color=theme.BG_DARK)

        self.session_repository = session_repository
        self.raw_chunk_repository = raw_chunk_repository
        self.packet_repository = packet_repository
        self.framing_config_repository = framing_config_repository
        self.exporter = exporter

        self._selected_session_id: int | None = None
        self._current_framing_mode = FramingMode.NONE
        self._current_framing_kwargs: dict = {}
        self._replay_queue: "queue.Queue" = queue.Queue()
        self._replay_thread: threading.Thread | None = None
        self._frame_parser = FrameParser(FramingMode.NONE)

        self._build_widgets()
        self._reload_session_list()

    def _build_widgets(self) -> None:
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=10)

        list_frame = tk.Frame(top_row, bg=theme.BG_PANEL)
        list_frame.pack(side="left", fill="both", expand=True)

        self.session_tree = ttk.Treeview(
            list_frame,
            columns=("name", "created", "rx", "tx", "chunks"),
            show="headings",
            style="Sniffer.Treeview",
            height=6,
        )
        for col, label, width in [
            ("name", "Nome", 220), ("created", "Início", 160),
            ("rx", "RX", 90), ("tx", "TX", 90), ("chunks", "Chunks", 80),
        ]:
            self.session_tree.heading(col, text=label)
            self.session_tree.column(col, width=width, anchor="w")
        self.session_tree.pack(side="left", fill="both", expand=True)
        self.session_tree.bind("<<TreeviewSelect>>", self._on_select_session)

        button_col = ctk.CTkFrame(top_row, fg_color="transparent")
        button_col.pack(side="left", padx=10)
        ctk.CTkButton(button_col, text="Abrir para revisão", command=self._open_review).pack(
            fill="x", pady=4
        )
        ctk.CTkButton(button_col, text="Configurar framing", command=self._open_framing_dialog).pack(
            fill="x", pady=4
        )
        ctk.CTkButton(button_col, text="Exportar CSV", command=lambda: self._export("csv")).pack(
            fill="x", pady=4
        )
        ctk.CTkButton(button_col, text="Exportar TXT (hexdump)",
                      command=lambda: self._export("txt")).pack(fill="x", pady=4)
        ctk.CTkButton(button_col, text="Atualizar lista", command=self._reload_session_list).pack(
            fill="x", pady=4
        )

        banner = ctk.CTkLabel(
            self, text="MODO REVISÃO — dados históricos, sem captura ao vivo",
            font=theme.FONT_UI_BOLD, text_color=theme.STATUS_CONNECTING,
        )
        banner.pack(pady=(0, 4))

        self.view = TwoColumnView(self, on_select=lambda _p: None)
        self.view.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_label = ctk.CTkLabel(self, text="", font=theme.FONT_UI)
        self.status_label.pack(pady=(0, 8))

    def _reload_session_list(self) -> None:
        self.session_tree.delete(*self.session_tree.get_children())
        for session in self.session_repository.list_sessions():
            self.session_tree.insert(
                "", "end", iid=str(session.id),
                values=(
                    session.name,
                    format_timestamp_ns(session.created_at_ns, with_micros=False),
                    session.rx_port,
                    session.tx_port,
                    session.raw_chunk_count,
                ),
            )

    def _on_select_session(self, _event=None) -> None:
        selection = self.session_tree.selection()
        if selection:
            self._selected_session_id = int(selection[0])

    def _open_framing_dialog(self) -> None:
        FramingConfigDialog(
            self,
            on_apply=self._apply_framing,
            initial_mode=self._current_framing_mode,
            initial_kwargs=self._current_framing_kwargs,
        )

    def _apply_framing(self, mode: FramingMode, kwargs: dict) -> None:
        self._frame_parser.set_strategy(mode, **kwargs)
        self._current_framing_mode = mode
        self._current_framing_kwargs = kwargs
        if self._selected_session_id is not None:
            self._open_review()

    def _open_review(self) -> None:
        if self._selected_session_id is None:
            self.status_label.configure(text="Selecione uma sessão na lista.")
            return
        self.view.clear()
        self._frame_parser.reset()
        self.status_label.configure(text="Carregando sessão...")

        session_id = self._selected_session_id
        self._replay_queue = queue.Queue()
        self._replay_thread = threading.Thread(
            target=self._stream_session, args=(session_id,), daemon=True
        )
        self._replay_thread.start()
        self.after(50, self._poll_replay_queue)

    def _stream_session(self, session_id: int) -> None:
        for event in self.raw_chunk_repository.stream_session(session_id):
            self._replay_queue.put(event)
        self._replay_queue.put(None)

    def _poll_replay_queue(self) -> None:
        processed = 0
        while processed < 500:
            try:
                item = self._replay_queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                self.status_label.configure(text="Sessão carregada.")
                for packet in self._frame_parser.flush_all():
                    self.view.add_packet(packet)
                return
            event: RawByteEvent = item
            for packet in self._frame_parser.feed(event):
                self.view.add_packet(packet)
            processed += 1
        self.after(30, self._poll_replay_queue)

    def _export(self, fmt: str) -> None:
        if self._selected_session_id is None:
            self.status_label.configure(text="Selecione uma sessão na lista.")
            return
        session = self.session_repository.get(self._selected_session_id)
        if not session:
            return
        default_name = f"{session.name}.{fmt}"
        dest = filedialog.asksaveasfilename(
            initialdir=str(EXPORT_DIR),
            initialfile=default_name,
            defaultextension=f".{fmt}",
            filetypes=[("CSV", "*.csv"), ("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not dest:
            return
        dest_path = Path(dest)
        if fmt == "csv":
            self.exporter.export_csv(session.id, dest_path, source="raw")
        else:
            self.exporter.export_hexdump_txt(session.id, dest_path, source="raw")
        self.status_label.configure(text=f"Exportado para {dest_path}")
