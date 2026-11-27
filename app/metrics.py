"""Rate maths and display formatting shared by the collector and the UI."""

from __future__ import annotations

import math
import re
from datetime import datetime
from ipaddress import ip_address

_MONO = ("Gbps", 1e9), ("Mbps", 1e6), ("Kbps", 1e3)


def compute_bps(previous_octets: int | None, current_octets: int,
                elapsed: float, counter_bits: int = 64) -> float | None:
    """Bits per second from two counter readings.

    Returns ``None`` for the first sample, for a stalled clock, or when a
    64-bit counter moved backwards (router reboot / counter reset).
    """
    if previous_octets is None or elapsed <= 0.05:
        return None
    delta = current_octets - previous_octets
    if delta < 0:
        if counter_bits == 32:
            delta += 1 << 32
        else:
            return None
    return delta * 8.0 / elapsed


def format_bps(bps: float | None) -> str:
    if bps is None:
        return "--"
    if bps < 0:
        bps = 0.0
    for unit, scale in _MONO:
        if bps >= scale:
            digits = 2 if unit == "Gbps" else 1
            return f"{bps / scale:.{digits}f} {unit}"
    return f"{bps:.0f} bps"


def format_bps_axis(value: float) -> str:
    """Compact axis label, e.g. ``250M`` / ``1.5G``."""
    value = abs(value)
    if value >= 1e9:
        return _trim(value / 1e9) + "G"
    if value >= 1e6:
        return _trim(value / 1e6) + "M"
    if value >= 1e3:
        return _trim(value / 1e3) + "k"
    return _trim(value)


def _trim(value: float) -> str:
    if value >= 10 or value == int(value):
        return f"{value:.0f}"
    return f"{value:.1f}"


def format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "--:--:--"
    total = int(max(0, seconds))
    days, total = divmod(total, 86_400)
    hours, total = divmod(total, 3_600)
    minutes, secs = divmod(total, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def nice_ceiling(value: float) -> float:
    """Round up to a friendly 1/2/5 x 10^n axis maximum."""
    if value <= 0:
        return 1.0
    magnitude = 10 ** int(f"{value:e}".split("e")[1])
    for step in (1, 2, 5, 10):
        candidate = step * magnitude
        if value <= candidate:
            return float(candidate)
    return float(10 * magnitude)


_UPTIME_PART = re.compile(r"(\d+)([wdhms])")
_UPTIME_SCALE = {"w": 604_800, "d": 86_400, "h": 3_600, "m": 60, "s": 1}


def parse_routeros_uptime(text: str | None) -> float | None:
    """Convert RouterOS uptime strings (``1w2d03:04:05``) to seconds."""
    if not text:
        return None
    remaining = text.strip()
    seconds = 0.0
    clock = re.search(r"(\d+):(\d+):(\d+)\s*$", remaining)
    if clock:
        seconds += int(clock.group(1)) * 3_600
        seconds += int(clock.group(2)) * 60
        seconds += int(clock.group(3))
        remaining = remaining[:clock.start()]
    for amount, unit in _UPTIME_PART.findall(remaining):
        seconds += int(amount) * _UPTIME_SCALE[unit]
    return seconds if seconds else None


def robust_peak(values, quantile: float = 0.95) -> float:
    """High percentile of the samples, so one counter glitch cannot dominate a chart."""
    positive = sorted(v for v in values if v is not None and v >= 0)
    if not positive:
        return 0.0
    index = min(len(positive) - 1, max(0, math.ceil(len(positive) * quantile) - 1))
    return positive[index]


def count_ip_ranges(ranges: str | None) -> int:
    """Number of addresses in RouterOS pool ranges like ``a-b,c``."""
    total = 0
    for part in (ranges or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            first, last = part.split("-", 1)
            total += int(ip_address(last.strip())) - int(ip_address(first.strip())) + 1
        else:
            total += 1
    return total


def smooth_series(xs, ys, subdivisions: int = 4):
    """Catmull-Rom interpolation for a rounded, non-jagged chart line."""
    count = len(xs)
    if count < 2:
        return list(xs), list(ys)
    out_x, out_y = [], []
    for i in range(count - 1):
        p0, p1, p2, p3 = max(0, i - 1), i, i + 1, min(count - 1, i + 2)
        x0, x1, x2, x3 = xs[p0], xs[p1], xs[p2], xs[p3]
        y0, y1, y2, y3 = ys[p0], ys[p1], ys[p2], ys[p3]
        for step in range(subdivisions):
            t = step / subdivisions
            t2, t3 = t * t, t * t * t
            out_x.append(0.5 * (
                2 * x1 + (-x0 + x2) * t
                + (2 * x0 - 5 * x1 + 4 * x2 - x3) * t2
                + (-x0 + 3 * x1 - 3 * x2 + x3) * t3
            ))
            value = 0.5 * (
                2 * y1 + (-y0 + y2) * t
                + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2
                + (-y0 + 3 * y1 - 3 * y2 + y3) * t3
            )
            out_y.append(max(0.0, value))
    out_x.append(xs[-1])
    out_y.append(max(0.0, ys[-1]))
    return out_x, out_y


def median_filter(values, width: int = 3) -> list:
    """Remove isolated counter glitches without shifting a sustained trend."""
    series = list(values)
    if not series:
        return []
    half = width // 2
    padded = [series[0]] * half + series + [series[-1]] * half
    return [
        sorted(padded[index:index + width])[half]
        for index in range(len(series))
    ]


def format_axis_clock(epoch: float, with_seconds: bool = False) -> str:
    """Clock label for a wall-clock X axis; include seconds on tight axes."""
    try:
        pattern = "%H:%M:%S" if with_seconds else "%H:%M"
        return datetime.fromtimestamp(float(epoch)).strftime(pattern)
    except (ValueError, OSError, TypeError, OverflowError):
        return "--:--:--" if with_seconds else "--:--"


def format_axis_ago(seconds: float) -> str:
    """Label a point's age on a relative time axis anchored at NOW."""
    ago = max(0.0, seconds)
    if ago < 1.0:
        return "NOW"
    if ago < 60.0:
        return f"-{ago:.0f}s"
    minutes, secs = divmod(int(round(ago)), 60)
    if secs == 0:
        return f"-{minutes}m"
    return f"-{minutes}m{secs:02d}s"
