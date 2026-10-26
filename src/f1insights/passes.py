"""On-track passes, using f1-debrief's pit and penalty filter."""

from __future__ import annotations

import re
from datetime import datetime

from f1debrief.select import PassEvent, Penalty, PitStop, on_track_passes

_CAR = re.compile(r"CAR\s+(\d+)")


def classify_overtakes(
    drivers: list[dict],
    overtakes: list[dict],
    pits: list[dict],
    control: list[dict],
) -> tuple[list[dict], list[PassEvent]]:
    """Return every swap, then the swaps f1-debrief keeps.

    The pit window and the penalty window are the library's. A pass index on
    this list is the index ``card_from_race`` uses for the same pair.
    """

    code_by_number = {
        int(driver["driver_number"]): str(driver.get("name_acronym") or driver["driver_number"])
        for driver in drivers
        if driver.get("driver_number") is not None
    }
    events = [
        PassEvent(
            date=_parse(row["date"]),
            overtaking=_code(code_by_number, row.get("overtaking_driver_number")),
            overtaken=_code(code_by_number, row.get("overtaken_driver_number")),
            position=None if row.get("position") is None else int(row["position"]),
        )
        for row in overtakes
        if row.get("date")
    ]
    pit_stops = [
        PitStop(date=_parse(row["date"]), driver=_code(code_by_number, row.get("driver_number")), duration_s=_duration(row))
        for row in pits
        if row.get("date")
    ]
    penalties = _penalties(control, code_by_number)
    kept = on_track_passes(events, pit_stops, penalties)
    pair_index: dict[tuple[str, str], int] = {}
    rows = []
    for event in kept:
        key = tuple(sorted((event.overtaking, event.overtaken)))
        index = pair_index.get(key, 0)
        pair_index[key] = index + 1
        rows.append(
            {
                "time": event.date.isoformat(),
                "overtaking": event.overtaking,
                "overtaken": event.overtaken,
                "position": event.position,
                "index": index,
            }
        )
    return rows, events


def _penalties(control: list[dict], code_by_number: dict[int, str]) -> list[Penalty]:
    found: list[Penalty] = []
    for row in control:
        message = str(row.get("message") or "")
        category = str(row.get("category") or "")
        if "PENALTY" not in message.upper() and "PENALTY" not in category.upper():
            continue
        if not row.get("date"):
            continue
        when = _parse(row["date"])
        number = row.get("driver_number")
        if isinstance(number, int):
            found.append(Penalty(date=when, driver=code_by_number.get(number, str(number))))
            continue
        for match in _CAR.findall(message.upper()):
            driver_number = int(match)
            found.append(Penalty(date=when, driver=code_by_number.get(driver_number, str(driver_number))))
    return found


def _duration(row: dict) -> float:
    for key in ("pit_duration", "lane_duration"):
        value = row.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 25.0


def _code(code_by_number: dict[int, str], number: object) -> str:
    if isinstance(number, int):
        return code_by_number.get(number, str(number))
    if isinstance(number, str) and number.isdigit():
        return code_by_number.get(int(number), number)
    return str(number or "?")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
