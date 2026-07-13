"""Cálculo de checksums/CRC comuns para validar hipóteses sobre o protocolo."""
from __future__ import annotations

from serial_sniffer.models.enums import ChecksumAlgorithm

_CRC8_POLY = 0x07
_CRC16_CCITT_POLY = 0x1021
_CRC16_MODBUS_POLY = 0xA001


class ChecksumCalculator:
    """Métodos estáticos de cálculo de checksum/CRC sobre uma sequência de bytes."""

    @staticmethod
    def xor(data: bytes) -> int:
        result = 0
        for b in data:
            result ^= b
        return result

    @staticmethod
    def sum8(data: bytes) -> int:
        return sum(data) & 0xFF

    @staticmethod
    def sum16(data: bytes) -> int:
        return sum(data) & 0xFFFF

    @staticmethod
    def crc8(data: bytes, poly: int = _CRC8_POLY, init: int = 0x00) -> int:
        crc = init
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ poly) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    @staticmethod
    def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
        crc = init
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ _CRC16_CCITT_POLY) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
        return crc

    @staticmethod
    def crc16_modbus(data: bytes, init: int = 0xFFFF) -> int:
        crc = init
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ _CRC16_MODBUS_POLY
                else:
                    crc >>= 1
        return crc

    @classmethod
    def compute(cls, data: bytes, algorithm: ChecksumAlgorithm) -> int:
        mapping = {
            ChecksumAlgorithm.XOR: cls.xor,
            ChecksumAlgorithm.SUM8: cls.sum8,
            ChecksumAlgorithm.SUM16: cls.sum16,
            ChecksumAlgorithm.CRC8: cls.crc8,
            ChecksumAlgorithm.CRC16_CCITT: cls.crc16_ccitt,
            ChecksumAlgorithm.CRC16_MODBUS: cls.crc16_modbus,
        }
        return mapping[algorithm](data)

    @classmethod
    def compute_all(cls, data: bytes) -> dict[str, int]:
        """Calcula todos os algoritmos de uma vez (usado ao persistir um Packet)."""
        if not data:
            return {}
        return {algo.value: cls.compute(data, algo) for algo in ChecksumAlgorithm}

    @classmethod
    def verify_last_byte(
        cls, data: bytes, algorithm: ChecksumAlgorithm
    ) -> tuple[bool, int, int]:
        """Testa se o último byte de `data` bate com o checksum dos bytes anteriores.

        Retorna (match, expected, actual) onde `actual` é o valor do último byte
        e `expected` é o checksum calculado sobre data[:-1].
        """
        if len(data) < 2:
            return False, 0, 0
        payload, last_byte = data[:-1], data[-1]
        expected = cls.compute(payload, algorithm) & 0xFF
        actual = last_byte
        return expected == actual, expected, actual
