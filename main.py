"""Ponto de entrada da aplicação do sniffer serial RS-232."""
import customtkinter as ctk

from serial_sniffer.config.settings import LOG_DIR, ensure_data_dirs
from serial_sniffer.ui.app import SnifferApp
from serial_sniffer.utils.logging_config import setup_logging


def main() -> None:
    ensure_data_dirs()
    setup_logging(LOG_DIR)

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = SnifferApp()
    app.mainloop()


if __name__ == "__main__":
    main()
