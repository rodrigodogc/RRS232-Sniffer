"""Constantes globais de configuração da aplicação."""
from pathlib import Path

APP_NAME = "RS-232 Sniffer"

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "sniffer_sessions.db"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = DATA_DIR / "logs"

# Captura serial
SERIAL_READ_TIMEOUT_S = 0.02
SERIAL_MAX_CHUNK_SIZE = 4096
RECONNECT_RETRY_INTERVAL_S = 2.0

# Gravação em banco (DBWriterThread)
DB_BATCH_MAX_SIZE = 500
DB_BATCH_INTERVAL_S = 0.1

# UI
UI_POLL_INTERVAL_MS = 80
UI_MAX_EVENTS_PER_TICK = 200
UI_MAX_VISIBLE_ROWS = 4000
UI_QUEUE_MAX_SIZE = 20000

# Framing
DELIMITER_MAX_BUFFER_SIZE = 8192

# Baud rates comuns para o seletor da UI
COMMON_BAUD_RATES = [
    1200, 2400, 4800, 9600, 14400, 19200,
    38400, 57600, 115200, 230400, 460800, 921600,
]

DEFAULT_BAUD_RATE = 9600

BYTESIZE_OPTIONS = [5, 6, 7, 8]
PARITY_OPTIONS = ["N", "E", "O", "M", "S"]
STOPBITS_OPTIONS = [1, 1.5, 2]


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
