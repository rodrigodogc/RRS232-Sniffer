"""Enumerações compartilhadas pelo domínio do sniffer."""
from enum import Enum


class PortRole(str, Enum):
    RX = "RX"
    TX = "TX"


class FramingMode(str, Enum):
    NONE = "NONE"
    DELIMITER = "DELIMITER"
    TIMEOUT = "TIMEOUT"
    FIXED_LENGTH = "FIXED_LENGTH"


class ChecksumAlgorithm(str, Enum):
    XOR = "XOR"
    SUM8 = "SUM8"
    SUM16 = "SUM16"
    CRC8 = "CRC8"
    CRC16_CCITT = "CRC16_CCITT"
    CRC16_MODBUS = "CRC16_MODBUS"


class ConnectionStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"
