"""Timestamp parsing/validation shared by the API and worker."""
from __future__ import annotations
import re

_TS = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)\s*$|^\s*(\d+(?:\.\d+)?)\s*$")


def parse_timestamp(text: str) -> float:
    """'83.5', '1:23.5' and '1:01:23' -> seconds."""
    m = _TS.match(text or "")
    if not m:
        raise ValueError(f"Unrecognized timestamp: {text!r}")
    if m.group(4) is not None:
        return float(m.group(4))
    a, b, c = m.group(1), m.group(2), float(m.group(3))
    if a is None:  # m:ss
        if float(b) >= 60 and c >= 60:
            raise ValueError("Seconds must be below 60")
        return int(b) * 60 + c
    return int(a) * 3600 + int(b) * 60 + c


def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    m, s = divmod(int(round(seconds * 10)) / 10, 60)
    return f"{int(m)}:{s:04.1f}"


def validate_range(start: float, end: float, duration: float, min_s: float, max_s: float) -> tuple[float, float]:
    """Return (start, end) rounded to 10 ms or raise ValueError with a user-facing message."""
    if start < 0 or end <= start:
        raise ValueError("End time must be after start time.")
    if end > duration + 0.05:
        raise ValueError(f"Selection ends after the track ({format_timestamp(duration)}).")
    end = min(end, duration)
    length = end - start
    if length < min_s:
        raise ValueError(f"Select at least {min_s:g} seconds.")
    if length > max_s:
        raise ValueError(f"Select at most {max_s:g} seconds, or use whole-song mode.")
    return round(start, 2), round(end, 2)


def make_windows(duration: float, length: float, hop: float) -> list[tuple[float, float]]:
    """Overlapping windows covering the track; the last window is anchored to the end."""
    if duration <= length:
        return [(0.0, round(duration, 2))]
    out, start = [], 0.0
    while start + length <= duration + 1e-6:
        out.append((round(start, 2), round(start + length, 2)))
        start += hop
    if out[-1][1] < duration - hop / 2:
        out.append((round(duration - length, 2), round(duration, 2)))
    return out


def cache_key(sha256: str, start: float, end: float, preprocess: str, model: str) -> str:
    return f"{sha256}:{start:.2f}:{end:.2f}:{preprocess}:{model}"
