from serial_sniffer.models.enums import ChecksumAlgorithm
from serial_sniffer.parsing.checksum import ChecksumCalculator


def test_xor_known_value():
    assert ChecksumCalculator.xor(bytes([0x01, 0x02, 0x03])) == 0x00
    assert ChecksumCalculator.xor(bytes([0xFF, 0x0F])) == 0xF0


def test_sum8_wraps_at_256():
    assert ChecksumCalculator.sum8(bytes([0xFF, 0x02])) == 0x01


def test_sum16_no_wrap_for_small_values():
    assert ChecksumCalculator.sum16(bytes([0x01, 0x02, 0x03])) == 6


def test_crc8_is_deterministic_and_sensitive_to_input():
    data_a = bytes([0x01, 0x02, 0x03])
    data_b = bytes([0x01, 0x02, 0x04])
    assert ChecksumCalculator.crc8(data_a) == ChecksumCalculator.crc8(data_a)
    assert ChecksumCalculator.crc8(data_a) != ChecksumCalculator.crc8(data_b)


def test_verify_last_byte_detects_matching_xor_checksum():
    payload = bytes([0x01, 0x02, 0x03])
    checksum = ChecksumCalculator.xor(payload)
    packet = payload + bytes([checksum])
    ok, expected, actual = ChecksumCalculator.verify_last_byte(packet, ChecksumAlgorithm.XOR)
    assert ok is True
    assert expected == actual == checksum


def test_verify_last_byte_detects_mismatch():
    packet = bytes([0x01, 0x02, 0x03, 0x99])
    ok, expected, actual = ChecksumCalculator.verify_last_byte(packet, ChecksumAlgorithm.XOR)
    assert ok is False
    assert actual == 0x99


def test_verify_last_byte_too_short_returns_false():
    ok, expected, actual = ChecksumCalculator.verify_last_byte(bytes([0x01]), ChecksumAlgorithm.XOR)
    assert ok is False


def test_compute_all_returns_every_algorithm():
    result = ChecksumCalculator.compute_all(bytes([0x01, 0x02]))
    assert set(result.keys()) == {a.value for a in ChecksumAlgorithm}
