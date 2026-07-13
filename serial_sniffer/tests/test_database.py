import sqlite3
from pathlib import Path

import pytest

from serial_sniffer.models.enums import FramingMode, PortRole
from serial_sniffer.models.packet import RawByteEvent
from serial_sniffer.models.session import FrameConfigDTO, Session
from serial_sniffer.storage.database import Database
from serial_sniffer.storage.framing_config_repository import FramingConfigRepository
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository
from serial_sniffer.storage.session_repository import SessionRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test_sessions.db")
    db.initialize_schema()
    yield db
    db.close()


def test_schema_initialization_is_idempotent(database: Database):
    database.initialize_schema()
    conn = database.connect()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"sessions", "raw_chunks", "framing_configs", "packets"}.issubset(tables)


def test_session_create_and_get(database: Database):
    repo = SessionRepository(database)
    session = Session(
        id=None, name="teste", created_at_ns=1000,
        rx_port="COM3", tx_port="COM4", rx_baud=9600, tx_baud=9600,
    )
    session_id = repo.create(session)
    fetched = repo.get(session_id)
    assert fetched is not None
    assert fetched.name == "teste"
    assert fetched.is_running is True


def test_session_update_end_marks_as_finished(database: Database):
    repo = SessionRepository(database)
    session_id = repo.create(Session(
        id=None, name="teste", created_at_ns=1000,
        rx_port="COM3", tx_port="COM4", rx_baud=9600, tx_baud=9600,
    ))
    repo.update_end(session_id, ended_at_ns=5000, raw_chunk_count=10,
                     total_bytes_rx=100, total_bytes_tx=50)
    fetched = repo.get(session_id)
    assert fetched.is_running is False
    assert fetched.raw_chunk_count == 10
    assert fetched.total_bytes_rx == 100


def test_raw_chunk_insert_and_stream_preserves_order(database: Database):
    session_repo = SessionRepository(database)
    chunk_repo = RawChunkRepository(database)
    session_id = session_repo.create(Session(
        id=None, name="teste", created_at_ns=1000,
        rx_port="COM3", tx_port="COM4", rx_baud=9600, tx_baud=9600,
    ))

    events = [
        RawByteEvent(port_role=PortRole.RX, timestamp_ns=i, seq=i, data=bytes([i % 256]))
        for i in range(250)
    ]
    chunk_repo.insert_batch(session_id, events)

    streamed = list(chunk_repo.stream_session(session_id, page_size=32))
    assert len(streamed) == 250
    assert [e.seq for e in streamed] == list(range(250))
    assert chunk_repo.count_for_session(session_id) == 250


def test_framing_config_deduplicates_identical_configs(database: Database):
    repo = FramingConfigRepository(database)
    dto = FrameConfigDTO(mode=FramingMode.DELIMITER, start_bytes=b"\x02", end_bytes=b"\x03")
    id_a = repo.get_or_create(dto, created_at_ns=1000)
    id_b = repo.get_or_create(dto, created_at_ns=2000)
    assert id_a == id_b


def test_framing_config_round_trips_escape_byte(database: Database):
    repo = FramingConfigRepository(database)
    dto = FrameConfigDTO(
        mode=FramingMode.DELIMITER, start_bytes=b"\x02", end_bytes=b"\x03",
        escape_byte=b"\x1B",
    )
    config_id = repo.get_or_create(dto, created_at_ns=1000)
    fetched = repo.get(config_id)
    assert fetched.escape_byte == b"\x1B"

    # uma config sem escape_byte não deve ser confundida com uma que tem
    dto_no_escape = FrameConfigDTO(mode=FramingMode.DELIMITER, start_bytes=b"\x02", end_bytes=b"\x03")
    other_id = repo.get_or_create(dto_no_escape, created_at_ns=2000)
    assert other_id != config_id


def test_schema_migration_adds_escape_byte_column_and_preserves_data(tmp_path: Path):
    db_path = tmp_path / "legacy.db"

    # monta manualmente um banco no schema ANTIGO (v1, sem escape_byte),
    # simulando um banco real já em uso antes desta migração existir
    legacy_conn = sqlite3.connect(str(db_path))
    legacy_conn.executescript(
        """
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version(version) VALUES (1);
        CREATE TABLE framing_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            mode TEXT NOT NULL,
            start_bytes BLOB,
            end_bytes BLOB,
            include_delimiters INTEGER NOT NULL DEFAULT 0,
            inter_byte_timeout_ms INTEGER,
            fixed_length INTEGER,
            created_at_ns INTEGER NOT NULL
        );
        INSERT INTO framing_configs (name, mode, start_bytes, end_bytes, include_delimiters, created_at_ns)
        VALUES ('legado', 'DELIMITER', X'02', X'03', 1, 1000);
        """
    )
    legacy_conn.commit()
    legacy_conn.close()

    db = Database(db_path)
    db.initialize_schema()
    conn = db.connect()

    columns = {row[1] for row in conn.execute("PRAGMA table_info(framing_configs)").fetchall()}
    assert "escape_byte" in columns

    preserved = conn.execute("SELECT name, mode FROM framing_configs WHERE name = 'legado'").fetchone()
    assert preserved is not None
    assert preserved["mode"] == "DELIMITER"

    version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert version == 2
    db.close()
