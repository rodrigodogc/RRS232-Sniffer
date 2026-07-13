"""Script standalone de simulação: envia pacotes binários realistas por uma porta
COM para validar o sniffer (RS-232 Sniffer) sem depender do hardware do fabricante.

Simula um controlador de eixo/robô reportando posição (X, Y), ângulo e offset,
intercalado com pacotes de heartbeat — útil para testar framing por delimitador
(STX/ETX) e verificação de checksum (XOR) na interface.

Uso:
    python testes.py
    python testes.py --port COM4 --baud 9600 --interval 0.2
    python testes.py --stuffing          # simula protocolo com byte-stuffing (escape 0x1B)
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import time

import serial
from serial import SerialException

STX = 0x02
ETX = 0x03
ESCAPE = 0x1B
_RESERVED_BYTES = {STX, ETX, ESCAPE}

CMD_POSITION_REPORT = 0x10
CMD_HEARTBEAT = 0x20

STATUS_MOVING = 0b001
STATUS_HOMED = 0b010
STATUS_ERROR = 0b100


class PacketSimulator:
    """Gera pacotes binários com dados de posição/ângulo/offset que variam no
    tempo, imitando a telemetria de um equipamento real em movimento.

    Dados binários crus podem coincidir por acaso com STX/ETX no meio do
    payload, cortando o pacote antes da hora em quem estiver ouvindo com
    framing por delimitador simples. Com use_stuffing=True, o simulador
    aplica byte-stuffing (escapa toda ocorrência literal de STX/ETX/ESCAPE
    dentro do corpo do pacote com o byte ESCAPE), como um protocolo bem
    projetado faria — o checksum continua sendo calculado sobre os bytes
    originais, antes do stuffing.
    """

    def __init__(self, use_stuffing: bool = False):
        self._start_time = time.monotonic()
        self._heartbeat_counter = 0
        self.use_stuffing = use_stuffing

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _simulate_axes(self) -> tuple[float, float, float, float]:
        t = self._elapsed()
        pos_x_mm = 500.0 + 300.0 * math.sin(t * 0.3)
        pos_y_mm = 300.0 + 200.0 * math.cos(t * 0.22)
        angle_deg = (t * 15.0) % 360.0 - 180.0
        offset_mm = 50.0 * math.sin(t * 0.5 + 1.0)
        return pos_x_mm, pos_y_mm, angle_deg, offset_mm

    @staticmethod
    def _xor_checksum(data: bytes) -> int:
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum

    @staticmethod
    def _stuff(data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            if b in _RESERVED_BYTES:
                out.append(ESCAPE)
            out.append(b)
        return bytes(out)

    def _frame(self, cmd: int, payload: bytes) -> bytes:
        body = bytes([cmd]) + payload
        # checksum sempre sobre os bytes originais, antes do stuffing —
        # o receptor precisa desfazer o escape antes de verificar
        checksum = self._xor_checksum(body)
        full_body = body + bytes([checksum])
        if self.use_stuffing:
            full_body = self._stuff(full_body)
        return bytes([STX]) + full_body + bytes([ETX])

    def next_position_packet(self) -> bytes:
        pos_x_mm, pos_y_mm, angle_deg, offset_mm = self._simulate_axes()

        status = STATUS_MOVING | STATUS_HOMED
        if int(self._elapsed()) % 17 == 0:
            status |= STATUS_ERROR

        payload = struct.pack(
            ">hhhhB",
            int(pos_x_mm * 10),
            int(pos_y_mm * 10),
            int(angle_deg * 10),
            int(offset_mm * 10),
            status,
        )
        return self._frame(CMD_POSITION_REPORT, payload)

    def next_heartbeat_packet(self) -> bytes:
        self._heartbeat_counter = (self._heartbeat_counter + 1) & 0xFFFF
        battery_pct = 80 + int(15 * math.sin(self._elapsed() * 0.05))
        payload = struct.pack(">HBB", self._heartbeat_counter, battery_pct, STATUS_HOMED)
        return self._frame(CMD_HEARTBEAT, payload)


class SerialTransmitter:
    """Abre uma porta COM em modo escrita e transmite pacotes simulados em loop."""

    def __init__(self, port: str, baud: int, interval_s: float, use_stuffing: bool = False):
        self.port = port
        self.baud = baud
        self.interval_s = interval_s
        self.use_stuffing = use_stuffing
        self._serial: serial.Serial | None = None

    def open(self) -> None:
        try:
            self._serial = serial.Serial(port=self.port, baudrate=self.baud, timeout=1)
        except SerialException as exc:
            message = str(exc).lower()
            if "permissionerror(13" in message or "errno 13" in message or "access is denied" in message:
                raise RuntimeError(
                    f"Porta {self.port} está ocupada por outro processo. Feche qualquer "
                    f"outro programa usando essa porta (ex: o próprio sniffer, terminal "
                    f"serial, Gerenciador de Dispositivos) e tente novamente."
                ) from exc
            raise RuntimeError(f"Falha ao abrir {self.port}: {exc}") from exc

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()

    def run(self, packet_count: int | None) -> None:
        simulator = PacketSimulator(use_stuffing=self.use_stuffing)
        sent = 0
        stuffing_note = "COM byte-stuffing (escape 0x1B)" if self.use_stuffing else "SEM byte-stuffing"
        print(f"Transmitindo em {self.port} @ {self.baud} bps a cada {self.interval_s}s "
              f"[{stuffing_note}] (Ctrl+C para parar)...\n")
        try:
            while packet_count is None or sent < packet_count:
                if sent % 5 == 4:
                    packet = simulator.next_heartbeat_packet()
                    label = "HEARTBEAT"
                else:
                    packet = simulator.next_position_packet()
                    label = "POSITION "

                self._serial.write(packet)
                self._serial.flush()

                hex_str = " ".join(f"{b:02X}" for b in packet)
                print(f"[{time.strftime('%H:%M:%S')}] {label} ({len(packet):2d} bytes): {hex_str}")

                sent += 1
                time.sleep(self.interval_s)
        except KeyboardInterrupt:
            print(f"\nInterrompido pelo usuário. {sent} pacotes enviados.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulador de tráfego serial para testar o RS-232 Sniffer"
    )
    parser.add_argument("--port", default="COM4", help="Porta COM de saída (padrão: COM4)")
    parser.add_argument("--baud", type=int, default=9600, help="Baud rate (padrão: 9600)")
    parser.add_argument(
        "--interval", type=float, default=0.2,
        help="Intervalo entre pacotes em segundos (padrão: 0.2)",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="Número de pacotes a enviar (padrão: infinito, até Ctrl+C)",
    )
    parser.add_argument(
        "--stuffing", action="store_true",
        help="Aplica byte-stuffing (escapa STX/ETX/ESC no payload com 0x1B), "
             "simulando um protocolo bem projetado. Configure o mesmo escape "
             "byte (1B) no diálogo de framing do sniffer para decodificar.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    transmitter = SerialTransmitter(
        port=args.port, baud=args.baud, interval_s=args.interval, use_stuffing=args.stuffing
    )
    try:
        transmitter.open()
    except RuntimeError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    try:
        transmitter.run(args.count)
    finally:
        transmitter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
