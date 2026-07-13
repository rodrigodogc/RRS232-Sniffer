"""Barra superior: seleção de portas COM, baud rate e controle Start/Stop."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk
from serial.tools import list_ports

from serial_sniffer.config.settings import COMMON_BAUD_RATES, DEFAULT_BAUD_RATE
from serial_sniffer.models.enums import ConnectionStatus
from serial_sniffer.models.session import CaptureConfig
from serial_sniffer.ui import theme
from serial_sniffer.utils.time_utils import default_session_name

_STATUS_COLOR = {
    ConnectionStatus.CONNECTED: theme.STATUS_CONNECTED,
    ConnectionStatus.CONNECTING: theme.STATUS_CONNECTING,
    ConnectionStatus.DISCONNECTED: theme.STATUS_DISCONNECTED,
    ConnectionStatus.ERROR: theme.STATUS_ERROR,
}


class TopBarFrame(ctk.CTkFrame):
    """Linha de controles para configurar e iniciar/parar uma sessão de captura."""

    def __init__(
        self,
        master,
        on_start: Callable[[CaptureConfig], None],
        on_stop: Callable[[], None],
        **kwargs,
    ):
        super().__init__(master, fg_color=theme.BG_PANEL, corner_radius=8, **kwargs)
        self.on_start = on_start
        self.on_stop = on_stop
        self._running = False

        self._build_widgets()
        self.refresh_ports()

    def _build_widgets(self) -> None:
        pad = {"padx": 6, "pady": 8}

        ctk.CTkLabel(self, text="Sessão:", font=theme.FONT_UI).grid(
            row=0, column=0, sticky="w", **pad
        )
        self.session_name_entry = ctk.CTkEntry(self, width=200)
        self.session_name_entry.insert(0, default_session_name())
        self.session_name_entry.grid(row=0, column=1, sticky="w", **pad)

        ctk.CTkLabel(self, text="Porta RX:", font=theme.FONT_UI, text_color=theme.RX_COLOR).grid(
            row=0, column=2, sticky="w", **pad
        )
        self.rx_port_combo = ctk.CTkComboBox(self, width=140, values=[])
        self.rx_port_combo.grid(row=0, column=3, **pad)

        ctk.CTkLabel(self, text="Baud RX:", font=theme.FONT_UI).grid(
            row=0, column=4, sticky="w", **pad
        )
        self.rx_baud_combo = ctk.CTkComboBox(
            self, width=100, values=[str(b) for b in COMMON_BAUD_RATES]
        )
        self.rx_baud_combo.set(str(DEFAULT_BAUD_RATE))
        self.rx_baud_combo.grid(row=0, column=5, **pad)

        ctk.CTkLabel(self, text="Porta TX:", font=theme.FONT_UI, text_color=theme.TX_COLOR).grid(
            row=0, column=6, sticky="w", **pad
        )
        self.tx_port_combo = ctk.CTkComboBox(self, width=140, values=[])
        self.tx_port_combo.grid(row=0, column=7, **pad)

        ctk.CTkLabel(self, text="Baud TX:", font=theme.FONT_UI).grid(
            row=0, column=8, sticky="w", **pad
        )
        self.tx_baud_combo = ctk.CTkComboBox(
            self, width=100, values=[str(b) for b in COMMON_BAUD_RATES]
        )
        self.tx_baud_combo.set(str(DEFAULT_BAUD_RATE))
        self.tx_baud_combo.grid(row=0, column=9, **pad)

        self.refresh_button = ctk.CTkButton(
            self, text="Atualizar portas", width=110, command=self.refresh_ports
        )
        self.refresh_button.grid(row=0, column=10, **pad)

        self.start_stop_button = ctk.CTkButton(
            self,
            text="Iniciar captura",
            width=140,
            fg_color=theme.STATUS_CONNECTED,
            hover_color="#3d8b40",
            command=self._toggle,
        )
        self.start_stop_button.grid(row=0, column=11, **pad)

        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=0, column=12, **pad)
        ctk.CTkLabel(status_frame, text="RX", font=theme.FONT_UI, text_color=theme.RX_COLOR).pack(
            side="left", padx=(0, 2)
        )
        self.rx_status_dot = ctk.CTkLabel(
            status_frame, text="●", text_color=theme.STATUS_DISCONNECTED, font=theme.FONT_UI_BOLD
        )
        self.rx_status_dot.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(status_frame, text="TX", font=theme.FONT_UI, text_color=theme.TX_COLOR).pack(
            side="left", padx=(0, 2)
        )
        self.tx_status_dot = ctk.CTkLabel(
            status_frame, text="●", text_color=theme.STATUS_DISCONNECTED, font=theme.FONT_UI_BOLD
        )
        self.tx_status_dot.pack(side="left")

    def refresh_ports(self) -> None:
        ports = [p.device for p in list_ports.comports()]
        if not ports:
            ports = ["(nenhuma porta encontrada)"]
        current_rx = self.rx_port_combo.get()
        current_tx = self.tx_port_combo.get()
        self.rx_port_combo.configure(values=ports)
        self.tx_port_combo.configure(values=ports)
        if current_rx in ports:
            self.rx_port_combo.set(current_rx)
        else:
            self.rx_port_combo.set(ports[0])
        if current_tx in ports:
            self.tx_port_combo.set(current_tx)
        elif len(ports) > 1:
            self.tx_port_combo.set(ports[1])
        else:
            self.tx_port_combo.set(ports[0])

    def _toggle(self) -> None:
        if self._running:
            self.on_stop()
        else:
            config = self._build_config()
            if config is not None:
                self.on_start(config)

    def _build_config(self) -> CaptureConfig | None:
        try:
            rx_baud = int(self.rx_baud_combo.get())
            tx_baud = int(self.tx_baud_combo.get())
        except ValueError:
            return None
        rx_port = self.rx_port_combo.get()
        tx_port = self.tx_port_combo.get()
        if not rx_port or not tx_port or "nenhuma porta" in rx_port:
            return None
        name = self.session_name_entry.get().strip() or default_session_name()
        return CaptureConfig(
            session_name=name,
            rx_port=rx_port,
            rx_baud=rx_baud,
            tx_port=tx_port,
            tx_baud=tx_baud,
        )

    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self.start_stop_button.configure(
                text="Parar captura", fg_color=theme.STATUS_ERROR, hover_color="#c62828"
            )
            self.session_name_entry.configure(state="disabled")
            self.rx_port_combo.configure(state="disabled")
            self.tx_port_combo.configure(state="disabled")
            self.rx_baud_combo.configure(state="disabled")
            self.tx_baud_combo.configure(state="disabled")
            self.refresh_button.configure(state="disabled")
        else:
            self.start_stop_button.configure(
                text="Iniciar captura", fg_color=theme.STATUS_CONNECTED, hover_color="#3d8b40"
            )
            self.session_name_entry.configure(state="normal")
            self.session_name_entry.delete(0, "end")
            self.session_name_entry.insert(0, default_session_name())
            self.rx_port_combo.configure(state="normal")
            self.tx_port_combo.configure(state="normal")
            self.rx_baud_combo.configure(state="normal")
            self.tx_baud_combo.configure(state="normal")
            self.refresh_button.configure(state="normal")

    def update_status(self, rx_status: ConnectionStatus, tx_status: ConnectionStatus) -> None:
        self.rx_status_dot.configure(text_color=_STATUS_COLOR[rx_status])
        self.tx_status_dot.configure(text_color=_STATUS_COLOR[tx_status])
