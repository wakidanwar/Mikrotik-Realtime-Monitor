"""ICMP latency probing via the Windows ``ping`` command.

Raw ICMP sockets need administrator rights on Windows, so the system
``ping.exe`` is used instead. Output is parsed with a locale-tolerant
regex (``time=12ms``, ``waktu=12ms``, ``time<1ms`` all match).
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from app.config import PingConfig, PingTargetConfig

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_RTT_PATTERN = re.compile(r"([=<])\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


@dataclass(frozen=True)
class PingStats:
    name: str
    host: str
    avg_ms: float | None
    loss_pct: float | None
    samples: int
    last_ms: float | None


def ping_once(host: str, timeout_ms: int) -> float | None:
    """Return the round-trip time in milliseconds, or None when unanswered."""
    command = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_ms / 1000 + 2.0,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None

    encoding = "oem" if sys.platform == "win32" else "utf-8"
    try:
        output = completed.stdout.decode(encoding, "replace")
    except LookupError:
        output = completed.stdout.decode("utf-8", "replace")

    match = _RTT_PATTERN.search(output)
    if not match:
        return None
    value = float(match.group(2).replace(",", "."))
    if match.group(1) == "<":
        value = min(value, 0.5)
    return value


class PingWindow:
    """Rolling window of ping samples used for average and packet loss."""

    def __init__(self, seconds: int):
        self.seconds = seconds
        self._samples: deque[tuple[float, float | None]] = deque()

    def add(self, timestamp: float, rtt: float | None) -> None:
        self._samples.append((timestamp, rtt))
        self._trim(timestamp)

    def _trim(self, now: float) -> None:
        cutoff = now - self.seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def stats(self, name: str, host: str, now: float) -> PingStats:
        self._trim(now)
        total = len(self._samples)
        if not total:
            return PingStats(name, host, None, None, 0, None)
        answered = [rtt for _ts, rtt in self._samples if rtt is not None]
        loss = (total - len(answered)) / total * 100.0
        average = sum(answered) / len(answered) if answered else None
        return PingStats(name, host, average, loss, total, self._samples[-1][1])


class PingWorker(threading.Thread):
    """Pings one target every interval and reports into the shared state."""

    def __init__(self, target: PingTargetConfig, config: PingConfig,
                 on_sample: Callable[[str, float | None], None],
                 stop_event: threading.Event):
        super().__init__(name=f"ping-{target.name}", daemon=True)
        self.target = target
        self.config = config
        self.on_sample = on_sample
        self.stop_event = stop_event

    def run(self) -> None:
        while not self.stop_event.is_set():
            started = time.monotonic()
            self.on_sample(self.target.name, ping_once(self.target.host, self.config.timeout_ms))
            elapsed = time.monotonic() - started
            self.stop_event.wait(max(0.05, self.config.interval - elapsed))
