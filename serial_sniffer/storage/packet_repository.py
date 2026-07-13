"""Persistência da tabela `packets` (cache derivado de uma config de framing)."""
from __future__ import annotations

from serial_sniffer.models.enums import ChecksumAlgorithm
from serial_sniffer.models.packet import Packet
from serial_sniffer.storage.database import Database


class PacketRepository:
    def __init__(self, database: Database):
        self.db = database

    def insert_batch(
        self, session_id: int, framing_config_id: int, packets: list[Packet]
    ) -> None:
        if not packets:
            return
        conn = self.db.connect()
        conn.executemany(
            """
            INSERT INTO packets (
                session_id, framing_config_id, port_role, seq,
                start_timestamp_ns, end_timestamp_ns, data, byte_count,
                checksum_xor, checksum_sum8, checksum_crc8, checksum_crc16,
                last_byte_match_algo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    framing_config_id,
                    p.port_role.value,
                    p.seq,
                    p.start_timestamp_ns,
                    p.end_timestamp_ns,
                    p.data,
                    p.byte_count,
                    p.checksums.get(ChecksumAlgorithm.XOR.value),
                    p.checksums.get(ChecksumAlgorithm.SUM8.value),
                    p.checksums.get(ChecksumAlgorithm.CRC8.value),
                    p.checksums.get(ChecksumAlgorithm.CRC16_CCITT.value),
                    p.last_byte_match_algo,
                )
                for p in packets
            ],
        )
        conn.commit()

    def delete_for_config(self, session_id: int, framing_config_id: int) -> None:
        conn = self.db.connect()
        conn.execute(
            "DELETE FROM packets WHERE session_id = ? AND framing_config_id = ?",
            (session_id, framing_config_id),
        )
        conn.commit()

    def list_for_session(self, session_id: int, framing_config_id: int) -> list[Packet]:
        from serial_sniffer.models.enums import PortRole

        conn = self.db.connect()
        rows = conn.execute(
            """
            SELECT * FROM packets
            WHERE session_id = ? AND framing_config_id = ?
            ORDER BY seq ASC
            """,
            (session_id, framing_config_id),
        ).fetchall()
        result = []
        for row in rows:
            result.append(
                Packet(
                    id=row["id"],
                    session_id=row["session_id"],
                    framing_config_id=row["framing_config_id"],
                    port_role=PortRole(row["port_role"]),
                    seq=row["seq"],
                    start_timestamp_ns=row["start_timestamp_ns"],
                    end_timestamp_ns=row["end_timestamp_ns"],
                    data=bytes(row["data"]),
                    last_byte_match_algo=row["last_byte_match_algo"],
                )
            )
        return result
