"""Paleta de cores e constantes visuais compartilhadas pela UI."""
import tkinter.ttk as ttk

BG_DARK = "#1a1a1f"
BG_PANEL = "#232329"
BG_ROW_ALT = "#2a2a32"
FG_TEXT = "#e6e6eb"
FG_MUTED = "#8b8b96"

RX_COLOR = "#4fc3f7"
TX_COLOR = "#ffb74d"
RX_ROW_BG = "#132733"
TX_ROW_BG = "#332616"

STATUS_CONNECTED = "#4caf50"
STATUS_CONNECTING = "#ffc107"
STATUS_DISCONNECTED = "#757575"
STATUS_ERROR = "#f44336"

MATCH_OK = "#4caf50"
MATCH_FAIL = "#f44336"

HIGHLIGHT_BG = "#5c4a1a"

FONT_MONO = ("Consolas", 11)
FONT_MONO_BOLD = ("Consolas", 11, "bold")
FONT_UI = ("Segoe UI", 12)
FONT_UI_BOLD = ("Segoe UI", 12, "bold")


def apply_treeview_dark_style(style: ttk.Style) -> None:
    style.theme_use("clam")
    style.configure(
        "Sniffer.Treeview",
        background=BG_PANEL,
        fieldbackground=BG_PANEL,
        foreground=FG_TEXT,
        rowheight=24,
        borderwidth=0,
        font=FONT_MONO,
    )
    style.configure(
        "Sniffer.Treeview.Heading",
        background=BG_DARK,
        foreground=FG_TEXT,
        borderwidth=0,
        font=FONT_UI_BOLD,
    )
    style.map(
        "Sniffer.Treeview",
        background=[("selected", "#3d5afe")],
        foreground=[("selected", "#ffffff")],
    )
    style.layout("Sniffer.Treeview", style.layout("Treeview"))
