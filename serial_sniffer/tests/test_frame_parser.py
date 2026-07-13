from serial_sniffer.models.enums import PortRole
from serial_sniffer.models.packet import RawByteEvent
from serial_sniffer.parsing.frame_parser import (
    DelimiterFrameStrategy,
    FixedLengthFrameStrategy,
    NoFramingStrategy,
    TimeoutFrameStrategy,
)


def _event(data: bytes, ts: int, seq: int = 0, role: PortRole = PortRole.RX) -> RawByteEvent:
    return RawByteEvent(port_role=role, timestamp_ns=ts, seq=seq, data=data)


def test_no_framing_passthrough():
    strategy = NoFramingStrategy()
    packets = strategy.feed(_event(b"\x01\x02\x03", ts=1000))
    assert len(packets) == 1
    assert packets[0].data == b"\x01\x02\x03"


def test_delimiter_strategy_extracts_packet_between_stx_etx():
    strategy = DelimiterFrameStrategy(start_bytes=b"\x02", end_bytes=b"\x03")
    packets = strategy.feed(_event(b"\x02\xAA\xBB\x03", ts=1000))
    assert len(packets) == 1
    assert packets[0].data == b"\xAA\xBB"


def test_delimiter_strategy_ignores_bytes_before_start():
    strategy = DelimiterFrameStrategy(start_bytes=b"\x02", end_bytes=b"\x03")
    packets = strategy.feed(_event(b"\xFF\xFF\x02\xAA\x03", ts=1000))
    assert len(packets) == 1
    assert packets[0].data == b"\xAA"


def test_delimiter_strategy_without_start_bytes_uses_end_only():
    strategy = DelimiterFrameStrategy(start_bytes=None, end_bytes=b"\x0D\x0A")
    packets = strategy.feed(_event(b"hello\x0D\x0A", ts=1000))
    assert len(packets) == 1
    assert packets[0].data == b"hello"


def test_delimiter_strategy_multiple_packets_in_one_chunk():
    strategy = DelimiterFrameStrategy(start_bytes=b"\x02", end_bytes=b"\x03")
    packets = strategy.feed(_event(b"\x02AA\x03\x02BB\x03", ts=1000))
    assert [p.data for p in packets] == [b"AA", b"BB"]


def test_delimiter_strategy_include_delimiters_does_not_leak_garbage_before_start():
    # bytes soltos entre pacotes (ex: cauda de um pacote de outro protocolo)
    # não podem vazar para dentro do próximo pacote quando include_delimiters=True
    strategy = DelimiterFrameStrategy(
        start_bytes=b"\x02", end_bytes=b"\x03", include_delimiters=True
    )
    packets = strategy.feed(_event(b"\x02AA\x03\xF0\x03\x02BB\x03", ts=1000))
    assert [p.data for p in packets] == [b"\x02AA\x03", b"\x02BB\x03"]


def test_delimiter_strategy_flush_returns_pending_partial_packet():
    strategy = DelimiterFrameStrategy(start_bytes=b"\x02", end_bytes=b"\x03")
    strategy.feed(_event(b"\x02AA", ts=1000))
    pending = strategy.flush()
    assert pending is not None
    assert pending.data == b"AA"


def test_timeout_strategy_closes_after_silence():
    strategy = TimeoutFrameStrategy(inter_byte_timeout_ms=10)
    strategy.feed(_event(b"\x01\x02", ts=0))
    packets = strategy.feed(_event(b"\x03", ts=20_000_000))  # 20ms depois
    assert len(packets) == 1
    assert packets[0].data == b"\x01\x02"


def test_timeout_strategy_tick_closes_pending_without_new_bytes():
    strategy = TimeoutFrameStrategy(inter_byte_timeout_ms=10)
    strategy.feed(_event(b"\x01\x02", ts=0))
    packets = strategy.tick(now_ns=20_000_000)
    assert len(packets) == 1
    assert packets[0].data == b"\x01\x02"


def test_delimiter_strategy_without_escape_splits_on_embedded_delimiter_byte():
    # payload binário puro contendo um 0x03 "de verdade" no meio corta o
    # pacote cedo demais quando não há byte-stuffing configurado
    strategy = DelimiterFrameStrategy(start_bytes=b"\x02", end_bytes=b"\x03", include_delimiters=True)
    packet = bytes.fromhex("02 10 0A 82 06 66 03 86 FE ED 03 6D 03".replace(" ", ""))
    packets = strategy.feed(_event(packet, ts=0))
    assert len(packets) == 1
    assert packets[0].data == bytes.fromhex("02 10 0A 82 06 66 03".replace(" ", ""))


def test_delimiter_strategy_with_escape_reconstructs_full_payload():
    # o mesmo payload, mas com o 0x03 do meio escapado (byte-stuffing) deve
    # sair como um único pacote completo, com o escape removido
    strategy = DelimiterFrameStrategy(
        start_bytes=b"\x02", end_bytes=b"\x03", include_delimiters=True, escape_byte=b"\x1B",
    )
    original_payload = bytes.fromhex("10 0A 82 06 66 03 86 FE ED 03 6D".replace(" ", ""))
    checksum = 0
    for b in original_payload:
        checksum ^= b
    body = original_payload + bytes([checksum])
    stuffed = bytearray()
    for b in body:
        if b in (0x02, 0x03, 0x1B):
            stuffed.append(0x1B)
        stuffed.append(b)
    stream = bytes([0x02]) + bytes(stuffed) + bytes([0x03])

    packets = strategy.feed(_event(stream, ts=0))
    assert len(packets) == 1
    assert packets[0].data == bytes([0x02]) + body + bytes([0x03])


def test_delimiter_strategy_escape_only_active_while_armed():
    # bytes de escape fora de um pacote (procurando o start) não têm efeito
    strategy = DelimiterFrameStrategy(
        start_bytes=b"\x02", end_bytes=b"\x03", escape_byte=b"\x1B",
    )
    packets = strategy.feed(_event(b"\x1B\xFF\x02AA\x03", ts=0))
    assert len(packets) == 1
    assert packets[0].data == b"AA"


def test_fixed_length_strategy_splits_every_n_bytes():
    strategy = FixedLengthFrameStrategy(length=2)
    packets = strategy.feed(_event(b"\x01\x02\x03\x04\x05", ts=0))
    assert [p.data for p in packets] == [b"\x01\x02", b"\x03\x04"]
    pending = strategy.flush()
    assert pending.data == b"\x05"
