"""Downsample the public location stream for a track replay.

Coordinates are the timing map, in tenths of a metre. The ribbon is one
racing lap from that map, drawn at a nominal width so the circuit can be
seen. It is not a surveyed kerb line, and the cars still share one path.
"""

from __future__ import annotations

import math
from datetime import datetime

# A racing lap on the current calendar is longer than Monaco and shorter than
# a lap plus a trip through the pits. Sample-to-sample jumps larger than this
# are a gap in the stream, not a piece of the circuit.
_MIN_LAP_M = 2500.0
_MAX_LAP_M = 9000.0
_CLOSE_M = 40.0
_BREAK_M = 80.0
_TRACK_WIDTH_M = 14.0
_TRACK_POINTS = 700


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
        return {"step_s": step_s, "duration_s": 0, "cars": [], "track": [], "track_width_m": _TRACK_WIDTH_M}

    for samples in grouped.values():
        samples.sort(key=lambda sample: sample[0])
    track = _racing_line(grouped)
    for number, samples in grouped.items():
        kept: list[dict] = []
        last_t = -1e9
        for moment, x, y in samples:
            elapsed = (moment - t0).total_seconds()
            if elapsed + 1e-6 < last_t + step_s and kept:
                continue
            last_t = elapsed
            kept.append({"t": round(elapsed, 2), "x": round(x, 2), "y": round(y, 2)})
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
    return {
        "step_s": step_s,
        "duration_s": round(duration, 2),
        "cars": cars,
        "track": track,
        "track_width_m": _TRACK_WIDTH_M,
    }


def _racing_line(grouped: dict[int, list[tuple[datetime, float, float]]]) -> list[list[float]]:
    """One closed racing lap, from the driver who completed the most of them."""

    best: list[tuple[float, float]] | None = None
    best_count = -1
    fallback: list[tuple[float, float]] = []
    for samples in grouped.values():
        points = [(x, y) for _, x, y in samples]
        if len(points) > len(fallback):
            fallback = points
        laps = _closed_laps(points)
        if len(laps) > best_count:
            best_count = len(laps)
            best = _median_lap(laps)
    chosen = best if best else _longest_run(fallback)
    return _resample(_seal(chosen), _TRACK_POINTS)


def _closed_laps(points: list[tuple[float, float]]) -> list[tuple[float, list[tuple[float, float]]]]:
    laps: list[tuple[float, list[tuple[float, float]]]] = []
    index = 0
    last = len(points) - 1
    while index < last:
        x0, y0 = points[index]
        travel = 0.0
        closed: int | None = None
        cursor = index + 1
        while cursor <= last:
            step = math.hypot(points[cursor][0] - points[cursor - 1][0], points[cursor][1] - points[cursor - 1][1])
            if step > _BREAK_M:
                break
            travel += step
            if travel > _MAX_LAP_M:
                break
            if travel >= _MIN_LAP_M and math.hypot(points[cursor][0] - x0, points[cursor][1] - y0) <= _CLOSE_M:
                closed = cursor
                break
            cursor += 1
        if closed is None:
            index = max(index + 1, cursor)
            continue
        laps.append((travel, points[index : closed + 1]))
        index = closed
    return laps


def _median_lap(laps: list[tuple[float, list[tuple[float, float]]]]) -> list[tuple[float, float]] | None:
    if not laps:
        return None
    lengths = sorted(lap[0] for lap in laps)
    median = lengths[len(lengths) // 2]
    return min(laps, key=lambda lap: (abs(lap[0] - median), -len(lap[1])))[1]


def _longest_run(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    best: list[tuple[float, float]] = []
    run: list[tuple[float, float]] = []
    for point in points:
        if run:
            step = math.hypot(point[0] - run[-1][0], point[1] - run[-1][1])
            if step > _BREAK_M:
                if len(run) > len(best):
                    best = run
                run = []
        run.append(point)
    if len(run) > len(best):
        best = run
    return best


def _seal(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    if math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) <= _CLOSE_M:
        return points + [points[0]]
    return points


def _resample(points: list[tuple[float, float]], count: int) -> list[list[float]]:
    if len(points) < 2:
        return [[round(point[0], 1), round(point[1], 1)] for point in points]
    distance = [0.0]
    for left, right in zip(points, points[1:]):
        distance.append(distance[-1] + math.hypot(right[0] - left[0], right[1] - left[1]))
    total = distance[-1]
    if total <= 0:
        return [[round(points[0][0], 1), round(points[0][1], 1)]]
    count = max(2, count)
    step = total / (count - 1)
    cursor = 0
    sampled: list[list[float]] = []
    for index in range(count):
        target = index * step
        while cursor + 1 < len(distance) and distance[cursor + 1] < target:
            cursor += 1
        nxt = min(cursor + 1, len(points) - 1)
        span = distance[nxt] - distance[cursor]
        mix = 0.0 if span <= 0 else (target - distance[cursor]) / span
        x = points[cursor][0] + (points[nxt][0] - points[cursor][0]) * mix
        y = points[cursor][1] + (points[nxt][1] - points[cursor][1]) * mix
        sampled.append([round(x, 1), round(y, 1)])
    return sampled


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
