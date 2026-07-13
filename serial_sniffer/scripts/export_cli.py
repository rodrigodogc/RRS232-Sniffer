"""CLI para listar e exportar sessões salvas sem precisar abrir a UI.

Uso:
    python -m serial_sniffer.scripts.export_cli list
    python -m serial_sniffer.scripts.export_cli export <session_id> --format csv --dest saida.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from serial_sniffer.config.settings import DB_PATH, EXPORT_DIR, ensure_data_dirs
from serial_sniffer.storage.database import Database
from serial_sniffer.storage.exporter import SessionExporter
from serial_sniffer.storage.packet_repository import PacketRepository
from serial_sniffer.storage.raw_chunk_repository import RawChunkRepository
from serial_sniffer.storage.session_repository import SessionRepository
from serial_sniffer.utils.time_utils import format_timestamp_ns


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exportação de sessões do RS-232 Sniffer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="Lista as sessões salvas no banco")

    export_parser = subparsers.add_parser("export", help="Exporta uma sessão")
    export_parser.add_argument("session_id", type=int)
    export_parser.add_argument("--format", choices=["csv", "txt"], default="csv")
    export_parser.add_argument("--dest", type=str, default=None)
    export_parser.add_argument(
        "--source", choices=["raw", "packets"], default="raw",
        help="raw = bytes brutos; packets = pacotes já framed (requer --framing-config-id)",
    )
    export_parser.add_argument("--framing-config-id", type=int, default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_data_dirs()
    args = build_parser().parse_args(argv)

    database = Database(DB_PATH)
    database.initialize_schema()
    session_repository = SessionRepository(database)
    raw_chunk_repository = RawChunkRepository(database)
    packet_repository = PacketRepository(database)
    exporter = SessionExporter(raw_chunk_repository, packet_repository)

    if args.command == "list":
        sessions = session_repository.list_sessions()
        if not sessions:
            print("Nenhuma sessão encontrada.")
            return 0
        for s in sessions:
            status = "em andamento" if s.is_running else "encerrada"
            print(
                f"[{s.id}] {s.name} | {format_timestamp_ns(s.created_at_ns, with_micros=False)} "
                f"| RX={s.rx_port}@{s.rx_baud} TX={s.tx_port}@{s.tx_baud} "
                f"| {s.raw_chunk_count} chunks | {status}"
            )
        return 0

    if args.command == "export":
        session = session_repository.get(args.session_id)
        if not session:
            print(f"Sessão {args.session_id} não encontrada.", file=sys.stderr)
            return 1
        if args.source == "packets" and args.framing_config_id is None:
            print("--framing-config-id é obrigatório quando --source=packets", file=sys.stderr)
            return 1

        dest = Path(args.dest) if args.dest else EXPORT_DIR / f"{session.name}.{args.format}"
        if args.format == "csv":
            exporter.export_csv(session.id, dest, source=args.source,
                                 framing_config_id=args.framing_config_id)
        else:
            exporter.export_hexdump_txt(session.id, dest, source=args.source,
                                         framing_config_id=args.framing_config_id)
        print(f"Exportado para {dest}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
