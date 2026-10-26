"""Clock and number formatting for the timing feed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class Clock:
    """Render feed timestamps in the circuit's local time."""

    def __init__(self, gmt_offset: str | None) -> None:
        self.delta = _offset(gmt_offset)
        self.label = _offset_label(self.delta)

    def date(self, value: str | None) -> str:
        moment = _parse(value)
        if moment is None:
            return "—"
        local = moment.astimezone(timezone(self.delta))
        return f"{local.day} {local.strftime('%b %Y')}"

    def time(self, value: str | None) -> str:
        moment = _parse(value)
        if moment is None:
            return "—"
        return moment.astimezone(timezone(self.delta)).strftime("%H:%M:%S")


def format_lap(seconds: object) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "—"
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    if minutes:
        return f"{minutes}:{rest:06.3f}"
    return f"{rest:.3f}"


def format_duration(seconds: object) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "—"
    whole = int(seconds)
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    frac = seconds - whole
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}.{int(round(frac * 1000)):03d}"
    return f"{minutes}:{secs:02d}.{int(round(frac * 1000)):03d}"


def format_gap(value: object, *, position: object, dnf: bool, dns: bool, dsq: bool) -> str:
    if dsq:
        return "DSQ"
    if dns:
        return "DNS"
    if dnf:
        return "DNF"
    if position == 1:
        return "Leader"
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return f"+{value:.3f}"
    return str(value)


def format_points(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "0"
    if float(value) == int(value):
        return str(int(value))
    return f"{value:.1f}"


def format_name(value: object) -> str:
    """OpenF1 stores surnames in capitals. Render them as a person's name."""

    if not isinstance(value, str) or not value.strip():
        return ""
    words = []
    for word in value.split():
        if word.isupper() and len(word) > 1:
            words.append(word.capitalize())
        else:
            words.append(word)
    return " ".join(words)


def format_speed(value: object) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "—"
    return str(int(value))


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _offset(value: str | None) -> timedelta:
    if not value:
        return timedelta(0)
    text = value.strip()
    sign = 1
    if text.startswith("-"):
        sign = -1
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]
    parts = text.split(":")
    if len(parts) < 2:
        return timedelta(0)
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return timedelta(0)
    return sign * timedelta(hours=hours, minutes=minutes, seconds=seconds)


def _offset_label(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if minutes:
        return f"UTC{sign}{hours}:{minutes:02d}"
    return f"UTC{sign}{hours}"
