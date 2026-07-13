"""Persistência da tabela `sessions`."""
from __future__ import annotations

from serial_sniffer.models.session import Session
from serial_sniffer.storage.database import Database


class SessionRepository:
    def __init__(self, database: Database):
        self.db = database

    def create(self, session: Session) -> int:
        conn = self.db.connect()
        cur = conn.execute(
            """
            INSERT INTO sessions (
                name, created_at_ns, rx_port, tx_port, rx_baud, tx_baud,
                bytesize, parity, stopbits
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.name,
                session.created_at_ns,
                session.rx_port,
                session.tx_port,
                session.rx_baud,
                session.tx_baud,
                session.bytesize,
                session.parity,
                session.stopbits,
            ),
        )
        conn.commit()
        return cur.lastrowid

    def update_end(
        self,
        session_id: int,
        ended_at_ns: int,
        raw_chunk_count: int,
        total_bytes_rx: int,
        total_bytes_tx: int,
        default_framing_config_id: int | None = None,
    ) -> None:
        conn = self.db.connect()
        conn.execute(
            """
            UPDATE sessions
            SET ended_at_ns = ?, raw_chunk_count = ?, total_bytes_rx = ?,
                total_bytes_tx = ?, default_framing_config_id = COALESCE(?, default_framing_config_id)
            WHERE id = ?
            """,
            (ended_at_ns, raw_chunk_count, total_bytes_rx, total_bytes_tx,
             default_framing_config_id, session_id),
        )
        conn.commit()

    def update_notes(self, session_id: int, notes: str) -> None:
        conn = self.db.connect()
        conn.execute("UPDATE sessions SET notes = ? WHERE id = ?", (notes, session_id))
        conn.commit()

    def rename(self, session_id: int, new_name: str) -> None:
        conn = self.db.connect()
        conn.execute("UPDATE sessions SET name = ? WHERE id = ?", (new_name, session_id))
        conn.commit()

    def get(self, session_id: int) -> Session | None:
        conn = self.db.connect()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self) -> list[Session]:
        conn = self.db.connect()
        rows = conn.execute("SELECT * FROM sessions ORDER BY created_at_ns DESC").fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete(self, session_id: int) -> None:
        conn = self.db.connect()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()

    @staticmethod
    def _row_to_session(row) -> Session:
        return Session(
            id=row["id"],
            name=row["name"],
            created_at_ns=row["created_at_ns"],
            ended_at_ns=row["ended_at_ns"],
            rx_port=row["rx_port"],
            tx_port=row["tx_port"],
            rx_baud=row["rx_baud"],
            tx_baud=row["tx_baud"],
            bytesize=row["bytesize"],
            parity=row["parity"],
            stopbits=row["stopbits"],
            raw_chunk_count=row["raw_chunk_count"],
            total_bytes_rx=row["total_bytes_rx"],
            total_bytes_tx=row["total_bytes_tx"],
            default_framing_config_id=row["default_framing_config_id"],
            notes=row["notes"],
        )
