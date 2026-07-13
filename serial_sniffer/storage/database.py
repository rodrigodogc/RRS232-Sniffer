"""Conexão e schema do banco SQLite."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS sessions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    name                        TEXT NOT NULL,
    created_at_ns               INTEGER NOT NULL,
    ended_at_ns                 INTEGER,
    rx_port                     TEXT NOT NULL,
    tx_port                     TEXT NOT NULL,
    rx_baud                     INTEGER NOT NULL,
    tx_baud                     INTEGER NOT NULL,
    bytesize                    INTEGER NOT NULL DEFAULT 8,
    parity                      TEXT NOT NULL DEFAULT 'N',
    stopbits                    REAL NOT NULL DEFAULT 1,
    raw_chunk_count             INTEGER NOT NULL DEFAULT 0,
    total_bytes_rx              INTEGER NOT NULL DEFAULT 0,
    total_bytes_tx              INTEGER NOT NULL DEFAULT 0,
    default_framing_config_id   INTEGER REFERENCES framing_configs(id),
    notes                       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at_ns);

CREATE TABLE IF NOT EXISTS raw_chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,
    port_role     TEXT NOT NULL CHECK(port_role IN ('RX','TX')),
    timestamp_ns  INTEGER NOT NULL,
    data          BLOB NOT NULL,
    byte_count    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_chunks_session_seq ON raw_chunks(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_raw_chunks_session_ts  ON raw_chunks(session_id, timestamp_ns);

CREATE TABLE IF NOT EXISTS framing_configs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT,
    mode                    TEXT NOT NULL CHECK(mode IN ('NONE','DELIMITER','TIMEOUT','FIXED_LENGTH')),
    start_bytes             BLOB,
    end_bytes               BLOB,
    include_delimiters      INTEGER NOT NULL DEFAULT 0,
    inter_byte_timeout_ms   INTEGER,
    fixed_length            INTEGER,
    escape_byte             BLOB,
    created_at_ns           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS packets (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    framing_config_id     INTEGER NOT NULL REFERENCES framing_configs(id),
    port_role             TEXT NOT NULL CHECK(port_role IN ('RX','TX')),
    seq                   INTEGER NOT NULL,
    start_timestamp_ns    INTEGER NOT NULL,
    end_timestamp_ns      INTEGER NOT NULL,
    data                  BLOB NOT NULL,
    byte_count            INTEGER NOT NULL,
    checksum_xor          INTEGER,
    checksum_sum8         INTEGER,
    checksum_crc8         INTEGER,
    checksum_crc16        INTEGER,
    last_byte_match_algo  TEXT
);
CREATE INDEX IF NOT EXISTS idx_packets_session_config_seq
    ON packets(session_id, framing_config_id, seq);
"""

_SCHEMA_VERSION = 2

_MIGRATIONS: dict[int, str] = {
    2: "ALTER TABLE framing_configs ADD COLUMN escape_byte BLOB",
}


class Database:
    """Gerencia conexões SQLite (uma por thread) para um único arquivo .db."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._schema_ready = False

    def connect(self) -> sqlite3.Connection:
        """Retorna a conexão desta thread, criando-a se necessário (WAL habilitado)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def initialize_schema(self) -> None:
        with self._init_lock:
            if self._schema_ready:
                return
            conn = self.connect()
            conn.executescript(_SCHEMA_SQL)
            row = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
            if row[0] == 0:
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)", (_SCHEMA_VERSION,)
                )
                current_version = _SCHEMA_VERSION
            else:
                current_version = conn.execute(
                    "SELECT version FROM schema_version"
                ).fetchone()[0]

            for version, migration_sql in sorted(_MIGRATIONS.items()):
                if current_version < version:
                    conn.execute(migration_sql)
                    current_version = version

            conn.execute("UPDATE schema_version SET version = ?", (current_version,))
            conn.commit()
            self._schema_ready = True

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
