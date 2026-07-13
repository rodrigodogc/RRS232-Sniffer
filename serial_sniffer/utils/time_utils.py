"""Utilitários de timestamp de alta resolução.

Combina uma âncora de wall-clock (time.time_ns) com um contador monotônico
(time.perf_counter_ns) para que os timestamps de eventos sejam ao mesmo tempo
ordenáveis de forma confiável (monotônicos) e legíveis como data/hora real.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeAnchor:
    wallclock_ns: int
    perf_ns: int

    @classmethod
    def now(cls) -> "TimeAnchor":
        return cls(wallclock_ns=time.time_ns(), perf_ns=time.perf_counter_ns())

    def event_timestamp_ns(self) -> int:
        return self.wallclock_ns + (time.perf_counter_ns() - self.perf_ns)


def format_timestamp_ns(timestamp_ns: int, with_micros: bool = True) -> str:
    seconds, nanos = divmod(timestamp_ns, 1_000_000_000)
    dt = datetime.fromtimestamp(seconds)
    if with_micros:
        micros = nanos // 1000
        return f"{dt.strftime('%H:%M:%S')}.{micros:06d}"
    millis = nanos // 1_000_000
    return f"{dt.strftime('%H:%M:%S')}.{millis:03d}"


def default_session_name(timestamp_ns: int | None = None) -> str:
    ts = timestamp_ns if timestamp_ns is not None else time.time_ns()
    seconds = ts // 1_000_000_000
    dt = datetime.fromtimestamp(seconds)
    return dt.strftime("sessao_%Y-%m-%d_%H-%M-%S")
