"""Downsample the public location stream for a track replay.

Coordinates are the timing map, in tenths of a metre. Cars share one path,
so the drawing shows race order along that map.
"""

from __future__ import annotations

from datetime import datetime


def build_replay(locations: list[dict], drivers: list[dict], *, step_s: float = 2.0) -> dict:
    code_by_number = {
        int(driver["driver_number"]): str(driver.get("name_acronym") or driver["driver_number"])
        for driver in drivers
        if driver.get("driver_number") is not None
    }
    colour_by_number = {
        int(driver["driver_number"]): str(driver.get("team_colour") or "888888")
        for driver in drivers
        if driver.get("driver_number") is not None
    }
    grouped: dict[int, list[tuple[datetime, float, float]]] = {}
    for row in locations:
        number = row.get("driver_number")
        moment = _parse(row.get("date"))
        x = row.get("x")
        y = row.get("y")
        if not isinstance(number, int) or moment is None:
            continue
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        if x == 0 and y == 0:
            continue
        grouped.setdefault(number, []).append((moment, float(x) * 0.1, float(y) * 0.1))

    cars = []
    t0: datetime | None = None
    for samples in grouped.values():
        if samples:
            first = min(sample[0] for sample in samples)
            t0 = first if t0 is None else min(t0, first)
    if t0 is None:
        return {"step_s": step_s, "duration_s": 0, "cars": [], "track": []}

    track: list[list[float]] = []
    longest = 0
    for number, samples in grouped.items():
        samples.sort(key=lambda sample: sample[0])
        kept: list[dict] = []
        last_t = -1e9
        for moment, x, y in samples:
            elapsed = (moment - t0).total_seconds()
            if elapsed + 1e-6 < last_t + step_s and kept:
                continue
            last_t = elapsed
            kept.append({"t": round(elapsed, 2), "x": round(x, 2), "y": round(y, 2)})
        if len(samples) > longest:
            longest = len(samples)
            track = [[round(x, 1), round(y, 1)] for _, x, y in samples[:: max(1, len(samples) // 400)]]
        cars.append(
            {
                "code": code_by_number.get(number, str(number)),
                "colour": colour_by_number.get(number, "888888"),
                "samples": kept,
            }
        )
    duration = 0.0
    for car in cars:
        if car["samples"]:
            duration = max(duration, car["samples"][-1]["t"])
    cars.sort(key=lambda car: car["code"])
    return {"step_s": step_s, "duration_s": round(duration, 2), "cars": cars, "track": track}


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
