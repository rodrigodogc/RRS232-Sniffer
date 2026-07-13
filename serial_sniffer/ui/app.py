"""Janela principal da aplicação: integra captura, parsing, storage e views."""
from __future__ import annotations

import logging
import queue
import time

import customtkinter as ctk

from serial_sniffer.capture.capture_manager import CaptureSession
from serial_sniffer.capture.exceptions import CaptureAlreadyRunningError, PortOpenError
from serial_sniffer.config.settings import (
    DB_PATH,
    UI_MAX_EVENTS_PER_TICK,
    UI_POLL_INTERVAL_MS,
)
from serial_sniffer.models.enums import FramingMode
from serial_sniffer.models.packet import Packet
from serial_sniffer.models.session import CaptureConfig, FrameConfigDTO
from serial_sniffer.parsing.filter import ByteSequenceFilter
from serial_sniffer.parsing.frame_parser import FrameParser
from serial_sniffer.storage.database import Database
from serial_sniffer.storage.exporter import SessionExporter
from serial_sniffer.storage.framing_config_repository import FramingConfigRepository
from serial_sniffer.storage.packet_repository import PacketRepository
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository
from serial_sniffer.storage.session_repository import SessionRepository
from serial_sniffer.ui import theme
from serial_sniffer.ui.checksum_panel import ChecksumPanel
from serial_sniffer.ui.filter_bar import FilterBar
from serial_sniffer.ui.framing_config_dialog import FramingConfigDialog
from serial_sniffer.ui.session_browser import SessionBrowserWindow
from serial_sniffer.ui.status_bar import StatusBar
from serial_sniffer.ui.timeline_view import TimelineView
from serial_sniffer.ui.top_bar import TopBarFrame
from serial_sniffer.ui.two_column_view import TwoColumnView

logger = logging.getLogger(__name__)


class SnifferApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RS-232 Sniffer :)")
        self.geometry("1400x820")
        self.configure(fg_color=theme.BG_DARK)

        self.database = Database(DB_PATH)
        self.database.initialize_schema()
        self.session_repository = SessionRepository(self.database)
        self.raw_chunk_repository = RawChunkRepository(self.database)
        self.packet_repository = PacketRepository(self.database)
        self.framing_config_repository = FramingConfigRepository(self.database)
        self.exporter = SessionExporter(self.raw_chunk_repository, self.packet_repository)

        self.frame_parser = FrameParser(FramingMode.NONE)
        self.capture_session = CaptureSession(
            session_repository=self.session_repository,
            raw_chunk_repository=self.raw_chunk_repository,
            packet_repository=self.packet_repository,
            framing_config_repository=self.framing_config_repository,
            frame_parser=self.frame_parser,
        )

        self._current_filter = ByteSequenceFilter("")
        self._current_framing_mode = FramingMode.NONE
        self._current_framing_kwargs: dict = {}

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(UI_POLL_INTERVAL_MS, self._poll)

    def _build_widgets(self) -> None:
        self.top_bar = TopBarFrame(self, on_start=self._on_start, on_stop=self._on_stop)
        self.top_bar.pack(fill="x", padx=10, pady=(10, 4))

        control_row = ctk.CTkFrame(self, fg_color="transparent")
        control_row.pack(fill="x", padx=10, pady=4)

        self.view_switch = ctk.CTkSegmentedButton(
            control_row, values=["Duas colunas", "Timeline"], command=self._on_view_switch
        )
        self.view_switch.set("Duas colunas")
        self.view_switch.pack(side="left")

        ctk.CTkButton(
            control_row, text="Configurar framing", command=self._open_framing_dialog
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            control_row, text="Sessões salvas", command=self._open_session_browser
        ).pack(side="left", padx=8)

        self.framing_label = ctk.CTkLabel(
            control_row, text="Framing: Sem framing (bruto)", font=theme.FONT_UI,
            text_color=theme.FG_MUTED,
        )
        self.framing_label.pack(side="left", padx=12)

        self.filter_bar = FilterBar(control_row, on_change=self._on_filter_change)
        self.filter_bar.pack(side="right")

        self.view_container = ctk.CTkFrame(self, fg_color="transparent")
        self.view_container.pack(fill="both", expand=True, padx=10, pady=4)

        self.two_column_view = TwoColumnView(self.view_container, on_select=self._on_packet_select)
        self.timeline_view = TimelineView(self.view_container, on_select=self._on_packet_select)
        self.two_column_view.pack(fill="both", expand=True)

        self.checksum_panel = ChecksumPanel(self)
        self.checksum_panel.pack(fill="x", padx=10, pady=4)

        self.status_bar = StatusBar(self)
        self.status_bar.pack(fill="x", padx=10, pady=(4, 10))

    def _on_view_switch(self, value: str) -> None:
        self.two_column_view.pack_forget()
        self.timeline_view.pack_forget()
        if value == "Duas colunas":
            self.two_column_view.pack(fill="both", expand=True)
        else:
            self.timeline_view.pack(fill="both", expand=True)

    def _on_start(self, config: CaptureConfig) -> None:
        config.db_path = str(DB_PATH)
        self.two_column_view.clear()
        self.timeline_view.clear()
        self.checksum_panel.clear()
        try:
            session = self.capture_session.start(config)
        except (PortOpenError, CaptureAlreadyRunningError) as exc:
            self.status_bar.set_message(str(exc), is_error=True)
            return
        self.top_bar.set_running(True)
        self.status_bar.set_message(f"Capturando sessão '{session.name}'...")

    def _on_stop(self) -> None:
        session = self.capture_session.stop()
        self.top_bar.set_running(False)
        if session:
            self.status_bar.set_message(
                f"Sessão '{session.name}' encerrada — {session.raw_chunk_count} chunks, "
                f"{session.total_bytes_rx} bytes RX, {session.total_bytes_tx} bytes TX."
            )

    def _open_framing_dialog(self) -> None:
        FramingConfigDialog(
            self,
            on_apply=self._apply_framing_live,
            initial_mode=self._current_framing_mode,
            initial_kwargs=self._current_framing_kwargs,
        )

    def _apply_framing_live(self, mode: FramingMode, kwargs: dict) -> None:
        self.frame_parser.set_strategy(mode, **kwargs)
        self._current_framing_mode = mode
        self._current_framing_kwargs = kwargs
        label = mode.value
        if kwargs:
            label += " " + ", ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
        self.framing_label.configure(text=f"Framing: {label}")

        if self.capture_session.session is not None:
            dto = FrameConfigDTO(mode=mode, **kwargs)
            config_id = self.framing_config_repository.get_or_create(
                dto, created_at_ns=time.time_ns()
            )
            self.capture_session.session.default_framing_config_id = config_id

    def _open_session_browser(self) -> None:
        SessionBrowserWindow(
            self,
            session_repository=self.session_repository,
            raw_chunk_repository=self.raw_chunk_repository,
            packet_repository=self.packet_repository,
            framing_config_repository=self.framing_config_repository,
            exporter=self.exporter,
        )

    def _on_filter_change(self, byte_filter: ByteSequenceFilter) -> None:
        self._current_filter = byte_filter

    def _on_packet_select(self, packet: Packet) -> None:
        self.checksum_panel.show_packet(packet)

    def _display_packet(self, packet: Packet) -> None:
        highlighted = (not self._current_filter.is_empty) and self._current_filter.matches(packet.data)
        self.two_column_view.add_packet(packet, highlighted)
        self.timeline_view.add_packet(packet, highlighted)

    def _poll(self) -> None:
        if self.capture_session.is_running():
            processed = 0
            while processed < UI_MAX_EVENTS_PER_TICK:
                try:
                    event = self.capture_session.ui_queue.get_nowait()
                except queue.Empty:
                    break
                for packet in self.frame_parser.feed(event):
                    self._display_packet(packet)
                processed += 1

            for packet in self.capture_session.tick_framing():
                self._display_packet(packet)

            snapshot = self.capture_session.get_status_snapshot()
            self.top_bar.update_status(snapshot["rx_status"], snapshot["tx_status"])
            self.status_bar.update_snapshot(snapshot)

        self.after(UI_POLL_INTERVAL_MS, self._poll)

    def _on_close(self) -> None:
        if self.capture_session.is_running():
            self.capture_session.stop()
        self.database.close()
        self.destroy()
