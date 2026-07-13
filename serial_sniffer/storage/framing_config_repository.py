"""Persistência da tabela `framing_configs`, com deduplicação."""
from __future__ import annotations

from serial_sniffer.models.enums import FramingMode
from serial_sniffer.models.session import FrameConfigDTO
from serial_sniffer.storage.database import Database


class FramingConfigRepository:
    def __init__(self, database: Database):
        self.db = database

    def get_or_create(self, dto: FrameConfigDTO, created_at_ns: int) -> int:
        conn = self.db.connect()
        row = conn.execute(
            """
            SELECT id FROM framing_configs
            WHERE mode = ? AND start_bytes IS ? AND end_bytes IS ?
              AND include_delimiters = ? AND inter_byte_timeout_ms IS ?
              AND fixed_length IS ? AND escape_byte IS ?
            """,
            (
                dto.mode.value,
                dto.start_bytes,
                dto.end_bytes,
                int(dto.include_delimiters),
                dto.inter_byte_timeout_ms,
                dto.fixed_length,
                dto.escape_byte,
            ),
        ).fetchone()
        if row:
            return row["id"]

        cur = conn.execute(
            """
            INSERT INTO framing_configs (
                name, mode, start_bytes, end_bytes, include_delimiters,
                inter_byte_timeout_ms, fixed_length, escape_byte, created_at_ns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dto.name,
                dto.mode.value,
                dto.start_bytes,
                dto.end_bytes,
                int(dto.include_delimiters),
                dto.inter_byte_timeout_ms,
                dto.fixed_length,
                dto.escape_byte,
                created_at_ns,
            ),
        )
        conn.commit()
        return cur.lastrowid

    def get(self, config_id: int) -> FrameConfigDTO | None:
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM framing_configs WHERE id = ?", (config_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_dto(row)

    def list_all(self) -> list[FrameConfigDTO]:
        conn = self.db.connect()
        rows = conn.execute("SELECT * FROM framing_configs ORDER BY id DESC").fetchall()
        return [self._row_to_dto(row) for row in rows]

    @staticmethod
    def _row_to_dto(row) -> FrameConfigDTO:
        return FrameConfigDTO(
            id=row["id"],
            name=row["name"],
            mode=FramingMode(row["mode"]),
            start_bytes=row["start_bytes"],
            end_bytes=row["end_bytes"],
            include_delimiters=bool(row["include_delimiters"]),
            inter_byte_timeout_ms=row["inter_byte_timeout_ms"],
            fixed_length=row["fixed_length"],
            escape_byte=row["escape_byte"],
            created_at_ns=row["created_at_ns"],
        )
