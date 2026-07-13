"""Diálogo de configuração da estratégia de framing (delimitador/timeout/tamanho fixo)."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from serial_sniffer.models.enums import FramingMode
from serial_sniffer.ui import theme

_MODE_LABELS = {
    "Sem framing (bruto)": FramingMode.NONE,
    "Delimitador (início/fim)": FramingMode.DELIMITER,
    "Timeout entre bytes": FramingMode.TIMEOUT,
    "Tamanho fixo": FramingMode.FIXED_LENGTH,
}
_LABELS_BY_MODE = {mode: label for label, mode in _MODE_LABELS.items()}


def _format_hex_bytes(data: bytes | None) -> str:
    return data.hex().upper() if data else ""


def _parse_hex_bytes(text: str) -> bytes | None:
    text = text.strip()
    if not text:
        return None
    cleaned = text.replace(" ", "").replace("0x", "").replace(",", "")
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return None


class FramingConfigDialog(ctk.CTkToplevel):
    """Janela modal para configurar como os bytes brutos são agrupados em pacotes."""

    def __init__(
        self,
        master,
        on_apply: Callable[[FramingMode, dict], None],
        initial_mode: FramingMode = FramingMode.NONE,
        initial_kwargs: dict | None = None,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.title("Configuração de Framing")
        self.geometry("420x420")
        self.configure(fg_color=theme.BG_DARK)
        self.on_apply = on_apply
        self.transient(master)
        initial_kwargs = initial_kwargs or {}

        self.mode_var = ctk.StringVar(
            value=_LABELS_BY_MODE.get(initial_mode, "Sem framing (bruto)")
        )
        ctk.CTkLabel(self, text="Modo:", font=theme.FONT_UI).pack(anchor="w", padx=16, pady=(16, 4))
        self.mode_menu = ctk.CTkOptionMenu(
            self, values=list(_MODE_LABELS.keys()), variable=self.mode_var,
            command=self._on_mode_change,
        )
        self.mode_menu.pack(anchor="w", padx=16)

        self.delimiter_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.delimiter_frame, text="Bytes de início (hex, opcional):").pack(
            anchor="w", pady=(8, 2)
        )
        self.start_bytes_entry = ctk.CTkEntry(self.delimiter_frame, placeholder_text="ex: 02")
        self.start_bytes_entry.pack(anchor="w", fill="x")
        self.start_bytes_entry.insert(0, _format_hex_bytes(initial_kwargs.get("start_bytes")))
        ctk.CTkLabel(self.delimiter_frame, text="Bytes de fim (hex):").pack(anchor="w", pady=(8, 2))
        self.end_bytes_entry = ctk.CTkEntry(self.delimiter_frame, placeholder_text="ex: 03")
        self.end_bytes_entry.pack(anchor="w", fill="x")
        self.end_bytes_entry.insert(0, _format_hex_bytes(initial_kwargs.get("end_bytes")))
        self.include_delimiters_var = ctk.BooleanVar(
            value=initial_kwargs.get("include_delimiters", False)
        )
        ctk.CTkCheckBox(
            self.delimiter_frame, text="Incluir delimitadores no pacote",
            variable=self.include_delimiters_var,
        ).pack(anchor="w", pady=(8, 4))

        self.use_escape_var = ctk.BooleanVar(value=bool(initial_kwargs.get("escape_byte")))
        ctk.CTkCheckBox(
            self.delimiter_frame,
            text="Protocolo usa byte-stuffing (escape de STX/ETX no payload)",
            variable=self.use_escape_var,
            command=self._on_escape_toggle,
        ).pack(anchor="w", pady=(4, 2))
        self.escape_byte_entry = ctk.CTkEntry(self.delimiter_frame, placeholder_text="ex: 1B")
        self.escape_byte_entry.pack(anchor="w", fill="x")
        self.escape_byte_entry.insert(
            0, _format_hex_bytes(initial_kwargs.get("escape_byte")) or "1B"
        )
        ctk.CTkLabel(
            self.delimiter_frame,
            text="Sem escape, um byte de payload igual a start/end_bytes fecha o\n"
                 "pacote antes da hora (comum em dados binários não protegidos).",
            font=("Segoe UI", 10), text_color=theme.FG_MUTED, justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self.timeout_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.timeout_frame, text="Timeout entre bytes (ms):").pack(
            anchor="w", pady=(8, 2)
        )
        self.timeout_entry = ctk.CTkEntry(self.timeout_frame, placeholder_text="ex: 20")
        self.timeout_entry.pack(anchor="w", fill="x")
        if initial_kwargs.get("inter_byte_timeout_ms") is not None:
            self.timeout_entry.insert(0, str(initial_kwargs["inter_byte_timeout_ms"]))

        self.fixed_length_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.fixed_length_frame, text="Tamanho fixo do pacote (bytes):").pack(
            anchor="w", pady=(8, 2)
        )
        self.fixed_length_entry = ctk.CTkEntry(self.fixed_length_frame, placeholder_text="ex: 8")
        self.fixed_length_entry.pack(anchor="w", fill="x")
        if initial_kwargs.get("fixed_length") is not None:
            self.fixed_length_entry.insert(0, str(initial_kwargs["fixed_length"]))

        self._mode_frames = {
            FramingMode.DELIMITER: self.delimiter_frame,
            FramingMode.TIMEOUT: self.timeout_frame,
            FramingMode.FIXED_LENGTH: self.fixed_length_frame,
        }

        self.error_label = ctk.CTkLabel(self, text="", text_color=theme.STATUS_ERROR)
        self.error_label.pack(anchor="w", padx=16, pady=(4, 0))

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(side="bottom", fill="x", padx=16, pady=16)
        ctk.CTkButton(button_row, text="Aplicar", command=self._apply).pack(side="right")
        ctk.CTkButton(
            button_row, text="Cancelar", fg_color="transparent", border_width=1,
            command=self.destroy,
        ).pack(side="right", padx=8)

        self._on_mode_change(self.mode_var.get())
        self._on_escape_toggle()

    def _on_mode_change(self, _label: str) -> None:
        for frame in self._mode_frames.values():
            frame.pack_forget()
        mode = _MODE_LABELS[self.mode_var.get()]
        frame = self._mode_frames.get(mode)
        if frame:
            frame.pack(fill="x", padx=16)

    def _on_escape_toggle(self) -> None:
        state = "normal" if self.use_escape_var.get() else "disabled"
        self.escape_byte_entry.configure(state=state)

    def _apply(self) -> None:
        mode = _MODE_LABELS[self.mode_var.get()]
        kwargs: dict = {}

        if mode == FramingMode.DELIMITER:
            end_bytes = _parse_hex_bytes(self.end_bytes_entry.get())
            if not end_bytes:
                self.error_label.configure(text="Informe bytes de fim válidos em hex.")
                return
            kwargs["start_bytes"] = _parse_hex_bytes(self.start_bytes_entry.get())
            kwargs["end_bytes"] = end_bytes
            kwargs["include_delimiters"] = self.include_delimiters_var.get()

            if self.use_escape_var.get():
                escape_byte = _parse_hex_bytes(self.escape_byte_entry.get())
                if not escape_byte or len(escape_byte) != 1:
                    self.error_label.configure(text="Byte de escape deve ser exatamente 1 byte em hex.")
                    return
                kwargs["escape_byte"] = escape_byte
        elif mode == FramingMode.TIMEOUT:
            try:
                kwargs["inter_byte_timeout_ms"] = int(self.timeout_entry.get())
                if kwargs["inter_byte_timeout_ms"] <= 0:
                    raise ValueError
            except ValueError:
                self.error_label.configure(text="Informe um timeout válido em milissegundos.")
                return
        elif mode == FramingMode.FIXED_LENGTH:
            try:
                kwargs["fixed_length"] = int(self.fixed_length_entry.get())
                if kwargs["fixed_length"] <= 0:
                    raise ValueError
            except ValueError:
                self.error_label.configure(text="Informe um tamanho fixo válido.")
                return

        self.on_apply(mode, kwargs)
        self.destroy()
