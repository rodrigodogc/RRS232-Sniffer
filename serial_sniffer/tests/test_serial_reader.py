import itertools
import queue
import threading

import pytest
from serial import SerialException

from serial_sniffer.capture.exceptions import PortBusyError, PortOpenError
from serial_sniffer.capture.serial_reader import SerialPortReader
from serial_sniffer.models.enums import PortRole
from serial_sniffer.utils.time_utils import TimeAnchor


def _make_reader() -> SerialPortReader:
    return SerialPortReader(
        port_name="COM_FAKE",
        baud=9600,
        role=PortRole.RX,
        output_queue=queue.Queue(),
        seq_counter=itertools.count(),
        seq_lock=threading.Lock(),
        time_anchor=TimeAnchor.now(),
    )


def test_open_port_raises_port_busy_error_on_access_denied(monkeypatch):
    reader = _make_reader()

    def fake_serial(**kwargs):
        raise SerialException("could not open port 'COM_FAKE': Access is denied.")

    monkeypatch.setattr("serial_sniffer.capture.serial_reader.serial.Serial", fake_serial)

    with pytest.raises(PortBusyError):
        reader._open_port()


def test_open_port_raises_generic_open_error_for_other_failures(monkeypatch):
    reader = _make_reader()

    def fake_serial(**kwargs):
        raise SerialException("could not open port 'COM_FAKE': FileNotFoundError")

    monkeypatch.setattr("serial_sniffer.capture.serial_reader.serial.Serial", fake_serial)

    with pytest.raises(PortOpenError):
        reader._open_port()


def test_reconnect_policy_defaults():
    from serial_sniffer.capture.serial_reader import ReconnectPolicy

    policy = ReconnectPolicy()
    assert policy.retry_interval_s > 0
    assert policy.max_retries is None
