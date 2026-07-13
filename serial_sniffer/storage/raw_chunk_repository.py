"""Persistência da tabela `raw_chunks` (log imutável de bytes brutos)."""
from __future__ import annotations

from collections.abc import Iterator

from serial_sniffer.models.packet import RawByteEvent
from serial_sniffer.models.enums import PortRole
from serial_sniffer.storage.database import Database


class RawChunkRepository:
    def __init__(self, database: Database):
        self.db = database

    def insert_batch(self, session_id: int, events: list[RawByteEvent]) -> None:
        if not events:
            return
        conn = self.db.connect()
        conn.executemany(
            """
            INSERT INTO raw_chunks (session_id, seq, port_role, timestamp_ns, data, byte_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (session_id, e.seq, e.port_role.value, e.timestamp_ns, e.data, e.byte_count)
                for e in events
            ],
        )
        conn.commit()

    def stream_session(
        self, session_id: int, page_size: int = 1000
    ) -> Iterator[RawByteEvent]:
        """Gera RawByteEvents em ordem de `seq`, paginado (keyset) para não
        carregar sessões grandes inteiras na memória."""
        conn = self.db.connect()
        last_seq = -1
        while True:
            rows = conn.execute(
                """
                SELECT seq, port_role, timestamp_ns, data
                FROM raw_chunks
                WHERE session_id = ? AND seq > ?
                ORDER BY seq ASC
                LIMIT ?
                """,
                (session_id, last_seq, page_size),
            ).fetchall()
            if not rows:
                break
            for row in rows:
                yield RawByteEvent(
                    port_role=PortRole(row["port_role"]),
                    timestamp_ns=row["timestamp_ns"],
                    seq=row["seq"],
                    data=bytes(row["data"]),
                )
                last_seq = row["seq"]
            if len(rows) < page_size:
                break

    def count_for_session(self, session_id: int) -> int:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM raw_chunks WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0]
