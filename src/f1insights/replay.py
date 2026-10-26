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
_VIEW = 5
# OpenF1 car data: 0 and 1 are DRS closed. 8 is available, and 10, 12, 14 are open.
_DRS_ZONE = {8, 10, 12, 14}
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

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
                "number": number,
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


def enrich_replay(
    document: dict,
    *,
    locations: list[dict],
    car_rows: list[dict],
    positions: list[dict],
    laps: list[dict],
    weather: list[dict],
    driver_number: int | None,
) -> dict:
    """Add the race board and the DRS stretches to a replay document."""

    t0 = _stream_start(locations)
    document["view"] = _VIEW
    located = _driver_path(locations, driver_number) if driver_number is not None else []
    document["drs"] = mark_drs(document.get("track") or [], located, car_rows)
    places = _changes(positions, t0, "position", "p", hold_initial=True)
    started = _changes(laps, t0, "lap_number", "n", moment_key="date_start")
    race_start: float | None = None
    lap_total = 0
    for car in document.get("cars") or []:
        number = car.get("number")
        car["places"] = places.get(number, [])
        car["laps"] = started.get(number, [])
        for lap in car["laps"]:
            if lap["n"] == 1:
                race_start = lap["t"] if race_start is None else min(race_start, lap["t"])
            if isinstance(lap["n"], int) and lap["n"] > lap_total:
                lap_total = lap["n"]
    document["race_start_s"] = None if race_start is None else round(race_start, 2)
    document["lap_total"] = lap_total or None
    document["weather"] = _weather_samples(weather, t0)
    return document


def mark_drs(
    track: list[list[float]],
    located: list[tuple[datetime, float, float]],
    car_rows: list[dict],
) -> list[int]:
    """1 on the lap vertices where this car's data shows DRS available or open."""

    if len(track) < 2 or not located or not car_rows:
        return [0] * len(track)
    events: list[tuple[datetime, int]] = []
    for row in car_rows:
        moment = _parse(row.get("date"))
        code = _drs_code(row.get("drs"))
        if moment is None or code is None:
            continue
        events.append((moment, code))
    events.sort()
    if not events:
        return [0] * len(track)
    votes = [0] * len(track)
    cursor = 0
    current: int | None = None
    current_at: datetime | None = None
    for moment, x, y in sorted(located, key=lambda sample: sample[0]):
        while cursor < len(events) and events[cursor][0] <= moment:
            current_at, current = events[cursor]
            cursor += 1
        if current is None or current_at is None or current not in _DRS_ZONE:
            continue
        if (moment - current_at).total_seconds() > 1.0:
            continue
        index = _nearest(track, x, y, 25.0)
        if index is not None:
            votes[index] += 1
    if max(votes) < 1:
        return [0] * len(track)
    # One lap only brushes each vertex once, so a single hit counts. Smoothing
    # joins the straight and drops a lone sample.
    flags = [1 if count else 0 for count in votes]
    return _smooth_zones(flags, gap=8, shortest=8)


def _drs_code(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _nearest(track: list[list[float]], x: float, y: float, limit: float) -> int | None:
    best_index = None
    best = limit * limit
    for index, point in enumerate(track):
        distance = (point[0] - x) ** 2 + (point[1] - y) ** 2
        if distance <= best:
            best = distance
            best_index = index
    return best_index


def _smooth_zones(flags: list[int], *, gap: int, shortest: int) -> list[int]:
    count = len(flags)
    if not count:
        return flags
    filled = flags[:]
    index = 0
    while index < count:
        if filled[index]:
            index += 1
            continue
        end = index
        while end < count and not filled[end]:
            end += 1
        left = filled[(index - 1) % count]
        right = filled[end % count] if end < count else filled[0]
        if left and right and (end - index) <= gap:
            for cursor in range(index, end):
                filled[cursor] = 1
        index = max(end, index + 1)
    runs = _circular_runs(filled)
    for start, length in runs:
        if length >= shortest:
            continue
        for step in range(length):
            filled[(start + step) % count] = 0
    return filled


def _circular_runs(flags: list[int]) -> list[tuple[int, int]]:
    count = len(flags)
    if not any(flags):
        return []
    if all(flags):
        return [(0, count)]
    start = 0
    while flags[start]:
        start += 1
    runs: list[tuple[int, int]] = []
    index = start
    while index < start + count:
        if flags[index % count]:
            end = index
            while end < start + count and flags[end % count]:
                end += 1
            runs.append((index % count, end - index))
            index = end
        else:
            index += 1
    return runs


def has_open_drs(rows: list[dict]) -> bool:
    return any(_drs_code(row.get("drs")) in _DRS_ZONE for row in rows)


def compact_car(rows: list[dict]) -> list[tuple]:
    """Time-ordered telemetry, with a held value when a sample is blank."""

    series = []
    speed = gear = throttle = brake = drs = None
    for row in rows:
        moment = _parse(row.get("date"))
        if moment is None:
            continue
        speed = _hold_speed(row.get("speed"), speed)
        gear = _hold_gear(row.get("n_gear"), gear)
        throttle = _hold_pedal(row.get("throttle"), throttle)
        brake = _hold_pedal(row.get("brake"), brake)
        code = _drs_code(row.get("drs"))
        if code is not None:
            drs = 1 if code in (10, 12, 14) else 0
        series.append((moment, speed, gear, throttle, brake, drs))
    series.sort(key=lambda item: item[0])
    return series


def attach_telemetry(document: dict, series_by_driver: dict[int, list[tuple]], locations: list[dict]) -> dict:
    """Copy speed, gear, throttle, brake, and DRS onto each replay sample."""

    t0 = _stream_start(locations)
    if t0 is None:
        return document
    for car in document.get("cars") or []:
        series = series_by_driver.get(car.get("number")) or []
        cursor = 0
        current = None
        current_t = None
        for sample in car.get("samples") or []:
            while cursor < len(series) and (series[cursor][0] - t0).total_seconds() <= sample["t"] + 0.05:
                current = series[cursor]
                current_t = (current[0] - t0).total_seconds()
                cursor += 1
            fresh = current is not None and current_t is not None and sample["t"] - current_t <= 2.0
            sample["speed"] = current[1] if fresh else None
            sample["gear"] = current[2] if fresh else None
            sample["throttle"] = current[3] if fresh else None
            sample["brake"] = current[4] if fresh else None
            sample["drs"] = current[5] if fresh else None
    return document


def _hold_speed(value: object, previous: int | None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return previous
    if 0 <= float(value) <= 400:
        return int(value)
    return previous


def _hold_gear(value: object, previous: int | None) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return previous
    if 0 <= value <= 8:
        return value
    return previous


def _hold_pedal(value: object, previous: int | None) -> int | None:
    if isinstance(value, bool):
        return 100 if value else 0
    if not isinstance(value, (int, float)):
        return previous
    if float(value) > 100:
        return previous
    return max(0, min(100, int(value)))


def drivers_by_laps(laps: list[dict]) -> list[int]:
    """Drivers who completed the most laps, first."""

    furthest: dict[int, int] = {}
    for row in laps:
        number = row.get("driver_number")
        lap = row.get("lap_number")
        if isinstance(number, int) and isinstance(lap, int) and not isinstance(lap, bool):
            furthest[number] = max(furthest.get(number, 0), lap)
    return sorted(furthest, key=lambda number: furthest[number], reverse=True)


def _changes(
    rows: list[dict],
    t0: datetime | None,
    source: str,
    name: str,
    *,
    moment_key: str = "date",
    hold_initial: bool = False,
) -> dict[int, list[dict]]:
    grouped: dict[int, list[tuple[float, int]]] = {}
    before: dict[int, tuple[float, int]] = {}
    for row in rows:
        number = row.get("driver_number")
        value = row.get(source)
        moment = _parse(row.get(moment_key))
        if (
            not isinstance(number, int)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or moment is None
            or t0 is None
        ):
            continue
        elapsed = (moment - t0).total_seconds()
        if elapsed <= 0:
            if hold_initial:
                previous = before.get(number)
                if previous is None or elapsed >= previous[0]:
                    before[number] = (elapsed, value)
            continue
        grouped.setdefault(number, []).append((elapsed, value))
    for number, (_, value) in before.items():
        grouped.setdefault(number, []).insert(0, (0.0, value))
    result: dict[int, list[dict]] = {}
    for number, items in grouped.items():
        items.sort()
        kept: list[dict] = []
        for elapsed, value in items:
            if kept and kept[-1][name] == value:
                continue
            kept.append({"t": round(elapsed, 2), name: value})
        result[number] = kept
    return result


def _weather_samples(rows: list[dict], t0: datetime | None) -> list[dict]:
    samples = []
    for row in rows:
        moment = _parse(row.get("date"))
        if moment is None or t0 is None:
            continue
        elapsed = (moment - t0).total_seconds()
        samples.append(
            {
                "t": round(max(0.0, elapsed), 2),
                "air": _number(row.get("air_temperature")),
                "track": _number(row.get("track_temperature")),
                "humidity": _number(row.get("humidity")),
                "wind": _number(row.get("wind_speed")),
                "wind_from": _compass(row.get("wind_direction")),
                "rain": _number(row.get("rainfall")),
            }
        )
    samples.sort(key=lambda sample: sample["t"])
    return samples


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 1)


def _compass(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return _COMPASS[int((float(value) + 22.5) // 45) % 8]


def _stream_start(locations: list[dict]) -> datetime | None:
    start: datetime | None = None
    for row in locations:
        moment = _parse(row.get("date"))
        x = row.get("x")
        y = row.get("y")
        if moment is None or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        if x == 0 and y == 0:
            continue
        start = moment if start is None else min(start, moment)
    return start


def _driver_path(locations: list[dict], driver_number: int) -> list[tuple[datetime, float, float]]:
    path: list[tuple[datetime, float, float]] = []
    for row in locations:
        if row.get("driver_number") != driver_number:
            continue
        moment = _parse(row.get("date"))
        x = row.get("x")
        y = row.get("y")
        if moment is None or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        if x == 0 and y == 0:
            continue
        path.append((moment, float(x) * 0.1, float(y) * 0.1))
    path.sort(key=lambda sample: sample[0])
    return path


def busiest_driver(locations: list[dict]) -> int | None:
    counts: dict[int, int] = {}
    for row in locations:
        number = row.get("driver_number")
        x = row.get("x")
        y = row.get("y")
        if not isinstance(number, int) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        if x == 0 and y == 0:
            continue
        counts[number] = counts.get(number, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda number: counts[number])


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
