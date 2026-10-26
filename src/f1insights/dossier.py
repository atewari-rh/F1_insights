"""One race, assembled from the timing feed.

The pass list is filtered by f1-debrief. Everything else is the published
session: result, qualifying, laps, pits, stints, weather, and race control.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from f1insights.format import (
    Clock,
    format_duration,
    format_gap,
    format_lap,
    format_name,
    format_points,
    format_speed,
)
from f1insights.passes import classify_overtakes
from f1insights.source import SourceError, cache_max_age, fetch


def load_race(session_key: int) -> dict:
    sessions = fetch("sessions", session_key=session_key)
    if not sessions:
        raise SourceError(f"No session {session_key}")
    session = sessions[0]
    age = cache_max_age(session.get("date_end"))
    year = int(session["year"])
    meeting_key = session["meeting_key"]
    meetings = fetch("meetings", max_age_s=age, meeting_key=meeting_key, year=year)
    meeting = meetings[0] if meetings else {}
    weekend = fetch("sessions", max_age_s=age, meeting_key=meeting_key)
    warnings: list[str] = []
    drivers = _safe("drivers", age, warnings, "The driver list", session_key=session_key)
    result = _safe("session_result", age, warnings, "The race result", session_key=session_key)
    laps = _safe("laps", age, warnings, "Lap times", session_key=session_key)
    pits = _safe("pit", age, warnings, "Pit stops", session_key=session_key)
    stints = _safe("stints", age, warnings, "Tyre stints", session_key=session_key)
    weather = _safe("weather", age, warnings, "Weather", session_key=session_key)
    control = _safe("race_control", age, warnings, "Race control", session_key=session_key)
    overtakes = _safe("overtakes", age, warnings, "Overtakes", session_key=session_key)
    positions = _safe("position", age, warnings, "Positions", session_key=session_key)
    quali = next((row for row in weekend if row.get("session_name") == "Qualifying"), None)
    quali_result = (
        _safe("session_result", age, warnings, "Qualifying", session_key=quali["session_key"]) if quali else []
    )
    year_sessions = fetch("sessions", max_age_s=age, year=year)
    year_meetings = fetch("meetings", max_age_s=age, year=year)
    if not result and not any(note.startswith("The race result") for note in warnings):
        warnings.append("The race result has not been published.")
    if not laps and not any(note.startswith("Lap times") for note in warnings):
        warnings.append("Lap times are not in the feed for this session.")
    return assemble(
        meeting=meeting,
        session=session,
        weekend=weekend,
        drivers=drivers,
        result=result,
        quali_result=quali_result,
        laps=laps,
        pits=pits,
        stints=stints,
        weather=weather,
        control=control,
        overtakes=overtakes,
        positions=positions,
        year_meetings=year_meetings,
        year_sessions=year_sessions,
        warnings=warnings,
    )


def assemble(
    *,
    meeting: dict,
    session: dict,
    weekend: list[dict],
    drivers: list[dict],
    result: list[dict],
    quali_result: list[dict],
    laps: list[dict],
    pits: list[dict],
    stints: list[dict],
    weather: list[dict],
    control: list[dict],
    overtakes: list[dict],
    positions: list[dict],
    year_meetings: list[dict],
    year_sessions: list[dict],
    warnings: list[str] | None = None,
) -> dict:
    clock = Clock(session.get("gmt_offset") or meeting.get("gmt_offset"))
    by_number = {int(driver["driver_number"]): driver for driver in drivers if driver.get("driver_number") is not None}
    quali_pos = {
        int(row["driver_number"]): row.get("position")
        for row in quali_result
        if row.get("driver_number") is not None and isinstance(row.get("position"), int)
    }
    laps_by_driver: dict[int, list[dict]] = defaultdict(list)
    for lap in laps:
        if isinstance(lap.get("driver_number"), int):
            laps_by_driver[int(lap["driver_number"])].append(lap)
    classification = [
        _result_row(row, by_number, quali_pos, laps_by_driver.get(int(row["driver_number"]), []) if isinstance(row.get("driver_number"), int) else [])
        for row in sorted(result, key=_result_sort)
    ]
    on_track, raw_events = classify_overtakes(drivers, overtakes, pits, control)
    passes = [_pass_row(row, clock, laps, by_number) for row in on_track]
    fastest = _fastest(laps, by_number)
    return {
        "session_key": int(session["session_key"]),
        "year": int(session["year"]),
        "name": meeting.get("meeting_name") or session.get("location") or "Race",
        "official_name": meeting.get("meeting_official_name") or "",
        "location": session.get("location") or meeting.get("location") or "",
        "country": session.get("country_name") or meeting.get("country_name") or "",
        "circuit_image": meeting.get("circuit_image") or "",
        "date_label": clock.date(session.get("date_start")),
        "time_label": clock.label,
        "cancelled": bool(session.get("is_cancelled") or meeting.get("is_cancelled")),
        "lede": _lede(meeting, session, classification, fastest, control, len(raw_events), len(on_track), weather, quali_result, by_number),
        "warnings": list(warnings or []),
        "classification": classification,
        "qualifying": _qualifying(quali_result, by_number),
        "fastest": fastest,
        "sectors": _best_sectors(laps, by_number),
        "traps": _speed_traps(laps, by_number),
        "chart": _chart(laps, positions, by_number),
        "stints": _stints(stints, by_number, laps),
        "passes": passes,
        "raw_swaps": len(raw_events),
        "on_track": len(on_track),
        "pits": _pits(pits, clock, by_number),
        "control": _control(control, clock, by_number),
        "weather": _weather(weather, clock),
        "drivers_detail": _driver_laps(laps, by_number, classification),
        "rounds": _rounds(year_meetings, year_sessions),
        "recorded_pair": int(session["session_key"]) == 9590,
    }


def _safe(path: str, age: float | None, warnings: list[str], label: str, **params) -> list:
    try:
        return fetch(path, max_age_s=age, **params)
    except SourceError as exc:
        warnings.append(f"{label} could not be loaded. {exc}")
        return []


def _result_sort(row: dict) -> tuple:
    position = row.get("position")
    if isinstance(position, int):
        return (0, position)
    return (1, -(row.get("number_of_laps") or 0))


def _result_row(row: dict, by_number: dict[int, dict], quali_pos: dict[int, object], driver_laps: list[dict]) -> dict:
    number = row.get("driver_number")
    driver = by_number.get(int(number)) if isinstance(number, int) else None
    dnf = bool(row.get("dnf"))
    dns = bool(row.get("dns"))
    dsq = bool(row.get("dsq"))
    return {
        "position": row.get("position"),
        "code": (driver or {}).get("name_acronym") or (str(number) if number is not None else "—"),
        "name": format_name((driver or {}).get("full_name")),
        "team": (driver or {}).get("team_name") or "",
        "colour": (driver or {}).get("team_colour") or "888888",
        "headshot": (driver or {}).get("headshot_url") or "",
        "grid": quali_pos.get(int(number)) if isinstance(number, int) else None,
        "laps": row.get("number_of_laps"),
        "gap": format_gap(row.get("gap_to_leader"), position=row.get("position"), dnf=dnf, dns=dns, dsq=dsq),
        "time": _race_time(row, driver_laps),
        "points": format_points(row.get("points")),
        "number": number,
    }


def _race_time(row: dict, driver_laps: list[dict]) -> str:
    """Official duration when the feed has one. Otherwise the sum of that driver's laps."""

    if row.get("dns"):
        return "—"
    duration = row.get("duration")
    if isinstance(duration, (int, float)) and duration > 0:
        return format_duration(duration)
    expected = row.get("number_of_laps")
    timed = [
        float(lap["lap_duration"])
        for lap in driver_laps
        if isinstance(lap.get("lap_duration"), (int, float)) and lap["lap_duration"] > 0
    ]
    if not isinstance(expected, int) or expected <= 0 or len(timed) < expected:
        return "—"
    return format_duration(sum(timed))


def _qualifying(result: list[dict], by_number: dict[int, dict]) -> list[dict]:
    rows = []
    for row in sorted(result, key=_result_sort):
        if not isinstance(row.get("position"), int):
            continue
        number = row.get("driver_number")
        driver = by_number.get(int(number)) if isinstance(number, int) else None
        times = _quali_times(row.get("duration"))
        rows.append(
            {
                "position": row["position"],
                "code": (driver or {}).get("name_acronym") or str(number),
                "name": format_name((driver or {}).get("full_name")),
                "team": (driver or {}).get("team_name") or "",
                "colour": (driver or {}).get("team_colour") or "888888",
                "q1": times[0],
                "q2": times[1],
                "q3": times[2],
            }
        )
    return rows


def _quali_times(duration: object) -> list[str]:
    if isinstance(duration, list):
        cells = [format_lap(value) if isinstance(value, (int, float)) else "—" for value in duration[:3]]
        return (cells + ["—", "—", "—"])[:3]
    if isinstance(duration, (int, float)):
        return [format_lap(duration), "—", "—"]
    return ["—", "—", "—"]


def _fastest(laps: list[dict], by_number: dict[int, dict]) -> dict | None:
    valid = [
        lap
        for lap in laps
        if isinstance(lap.get("lap_duration"), (int, float))
        and lap["lap_duration"] > 30
        and not lap.get("is_pit_out_lap")
    ]
    if not valid:
        return None
    ordered = sorted(float(lap["lap_duration"]) for lap in valid)
    median = ordered[len(ordered) // 2]
    racing = [lap for lap in valid if float(lap["lap_duration"]) >= median * 0.9]
    pool = racing or valid
    best = min(pool, key=lambda lap: float(lap["lap_duration"]))
    driver = by_number.get(int(best["driver_number"])) if isinstance(best.get("driver_number"), int) else None
    return {
        "code": (driver or {}).get("name_acronym") or str(best.get("driver_number")),
        "name": format_name((driver or {}).get("full_name")),
        "colour": (driver or {}).get("team_colour") or "888888",
        "lap": best.get("lap_number"),
        "time": format_lap(best.get("lap_duration")),
        "st": format_speed(best.get("st_speed")),
    }


def _best_sectors(laps: list[dict], by_number: dict[int, dict]) -> list[dict]:
    found = []
    for key, label in (
        ("duration_sector_1", "Sector 1"),
        ("duration_sector_2", "Sector 2"),
        ("duration_sector_3", "Sector 3"),
    ):
        pool = [lap for lap in laps if isinstance(lap.get(key), (int, float)) and lap[key] > 0]
        if not pool:
            continue
        best = min(pool, key=lambda lap: float(lap[key]))
        driver = by_number.get(int(best["driver_number"])) if isinstance(best.get("driver_number"), int) else None
        found.append(
            {
                "name": label,
                "time": f"{float(best[key]):.3f}",
                "code": (driver or {}).get("name_acronym") or str(best.get("driver_number")),
                "lap": best.get("lap_number"),
            }
        )
    return found


def _speed_traps(laps: list[dict], by_number: dict[int, dict]) -> list[dict]:
    found = []
    for key, label in (("st_speed", "Speed trap"), ("i1_speed", "Intermediate 1"), ("i2_speed", "Intermediate 2")):
        pool = [lap for lap in laps if isinstance(lap.get(key), (int, float)) and lap[key] > 0]
        if not pool:
            continue
        best = max(pool, key=lambda lap: float(lap[key]))
        driver = by_number.get(int(best["driver_number"])) if isinstance(best.get("driver_number"), int) else None
        found.append(
            {
                "name": label,
                "speed": format_speed(best.get(key)),
                "code": (driver or {}).get("name_acronym") or str(best.get("driver_number")),
                "lap": best.get("lap_number"),
            }
        )
    return found


def _chart(laps: list[dict], positions: list[dict], by_number: dict[int, dict]) -> dict:
    by_driver_laps: dict[int, list[dict]] = defaultdict(list)
    for lap in laps:
        if isinstance(lap.get("driver_number"), int) and isinstance(lap.get("lap_number"), int):
            by_driver_laps[lap["driver_number"]].append(lap)
    by_driver_pos: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
    for row in positions:
        moment = _parse(row.get("date"))
        if isinstance(row.get("driver_number"), int) and isinstance(row.get("position"), int) and moment is not None:
            by_driver_pos[row["driver_number"]].append((moment, int(row["position"])))
    for samples in by_driver_pos.values():
        samples.sort(key=lambda item: item[0])
    max_lap = 0
    for driver_laps in by_driver_laps.values():
        if driver_laps:
            max_lap = max(max_lap, max(int(lap["lap_number"]) for lap in driver_laps))
    if max_lap == 0 or not by_driver_pos:
        return {"laps": [], "series": []}
    series = []
    for number, driver_laps in by_driver_laps.items():
        driver_laps.sort(key=lambda lap: int(lap["lap_number"]))
        samples = by_driver_pos.get(number, [])
        cursor = 0
        last = None
        place = [None] * max_lap
        for lap in driver_laps:
            moment = _parse(lap.get("date_start"))
            if moment is None:
                continue
            while cursor < len(samples) and samples[cursor][0] <= moment:
                last = samples[cursor][1]
                cursor += 1
            index = int(lap["lap_number"]) - 1
            if 0 <= index < max_lap:
                place[index] = last
        driver = by_number.get(number, {})
        series.append(
            {
                "code": driver.get("name_acronym") or str(number),
                "colour": driver.get("team_colour") or "888888",
                "positions": place,
            }
        )
    series.sort(key=lambda row: row["code"])
    return {"laps": list(range(1, max_lap + 1)), "series": series}


def _stints(stints: list[dict], by_number: dict[int, dict], laps: list[dict]) -> list[dict]:
    total = 0
    for lap in laps:
        if isinstance(lap.get("lap_number"), int):
            total = max(total, int(lap["lap_number"]))
    for stint in stints:
        if isinstance(stint.get("lap_end"), int):
            total = max(total, int(stint["lap_end"]))
    if total <= 0:
        return []
    grouped: dict[int, list[dict]] = defaultdict(list)
    for stint in stints:
        if isinstance(stint.get("driver_number"), int):
            grouped[stint["driver_number"]].append(stint)
    rows = []
    for number, driver_stints in grouped.items():
        driver = by_number.get(number, {})
        pieces = []
        for stint in sorted(driver_stints, key=lambda item: item.get("stint_number") or 0):
            start = int(stint.get("lap_start") or 1)
            end = int(stint.get("lap_end") or start)
            pieces.append(
                {
                    "compound": str(stint.get("compound") or "UNKNOWN").upper(),
                    "start": start,
                    "end": end,
                    "age": stint.get("tyre_age_at_start"),
                    "width": max(1.0, (end - start + 1) / total * 100),
                }
            )
        rows.append(
            {
                "code": driver.get("name_acronym") or str(number),
                "colour": driver.get("team_colour") or "888888",
                "stints": pieces,
            }
        )
    rows.sort(key=lambda row: row["code"])
    return rows


def _pits(pits: list[dict], clock: Clock, by_number: dict[int, dict]) -> list[dict]:
    rows = []
    for pit in sorted(pits, key=lambda row: row.get("date") or ""):
        number = pit.get("driver_number")
        driver = by_number.get(int(number)) if isinstance(number, int) else None
        rows.append(
            {
                "time": clock.time(pit.get("date")),
                "code": (driver or {}).get("name_acronym") or str(number),
                "colour": (driver or {}).get("team_colour") or "888888",
                "lap": pit.get("lap_number"),
                "stop": _seconds(pit.get("stop_duration")),
                "lane": _seconds(pit.get("lane_duration")),
                "total": _seconds(pit.get("pit_duration")),
            }
        )
    return rows


def _control(control: list[dict], clock: Clock, by_number: dict[int, dict]) -> list[dict]:
    rows = []
    for message in sorted(control, key=lambda row: row.get("date") or ""):
        number = message.get("driver_number")
        driver = by_number.get(int(number)) if isinstance(number, int) else None
        text = str(message.get("message") or "")
        flag = message.get("flag") or ""
        rows.append(
            {
                "time": clock.time(message.get("date")),
                "lap": message.get("lap_number"),
                "category": message.get("category") or "",
                "flag": flag,
                "code": (driver or {}).get("name_acronym") or "",
                "message": text,
                "tone": _tone(flag, text),
            }
        )
    return rows


def _weather(weather: list[dict], clock: Clock) -> dict | None:
    rows = [row for row in weather if row.get("date")]
    if not rows:
        return None
    rows.sort(key=lambda row: row["date"])
    rain = any(isinstance(row.get("rainfall"), (int, float)) and row["rainfall"] > 0 for row in rows)

    def sample(row: dict) -> dict:
        return {
            "time": clock.time(row.get("date")),
            "air": row.get("air_temperature"),
            "track": row.get("track_temperature"),
            "humidity": row.get("humidity"),
            "wind": row.get("wind_speed"),
            "rain": row.get("rainfall"),
        }

    return {
        "rain": rain,
        "first": sample(rows[0]),
        "last": sample(rows[-1]),
        "samples": [sample(row) for row in rows],
    }


def _driver_laps(laps: list[dict], by_number: dict[int, dict], classification: list[dict]) -> list[dict]:
    order = {row["code"]: index for index, row in enumerate(classification)}
    grouped: dict[int, list[dict]] = defaultdict(list)
    for lap in laps:
        if isinstance(lap.get("driver_number"), int):
            grouped[lap["driver_number"]].append(lap)
    rows = []
    for number, driver_laps in grouped.items():
        driver = by_number.get(number, {})
        code = driver.get("name_acronym") or str(number)
        pieces = []
        for lap in sorted(driver_laps, key=lambda item: item.get("lap_number") or 0):
            pieces.append(
                {
                    "n": lap.get("lap_number"),
                    "time": format_lap(lap.get("lap_duration")),
                    "s1": _sector(lap.get("duration_sector_1")),
                    "s2": _sector(lap.get("duration_sector_2")),
                    "s3": _sector(lap.get("duration_sector_3")),
                    "pit": bool(lap.get("is_pit_out_lap")),
                    "st": format_speed(lap.get("st_speed")),
                    "i1": format_speed(lap.get("i1_speed")),
                    "i2": format_speed(lap.get("i2_speed")),
                }
            )
        rows.append(
            {
                "code": code,
                "name": format_name(driver.get("full_name")),
                "team": driver.get("team_name") or "",
                "colour": driver.get("team_colour") or "888888",
                "laps": pieces,
                "order": order.get(code, 100),
            }
        )
    rows.sort(key=lambda row: (row["order"], row["code"]))
    return rows


def _pass_row(row: dict, clock: Clock, laps: list[dict], by_number: dict[int, dict]) -> dict:
    number = next(
        (driver_number for driver_number, driver in by_number.items() if driver.get("name_acronym") == row["overtaking"]),
        None,
    )
    lap_number = _lap_at(laps, number, row["time"])
    return {
        "time": clock.time(row["time"]),
        "overtaking": row["overtaking"],
        "overtaken": row["overtaken"],
        "position": row["position"],
        "index": row["index"],
        "lap": lap_number,
    }


def _lap_at(laps: list[dict], number: int | None, when: str) -> int | None:
    if number is None:
        return None
    moment = _parse(when)
    if moment is None:
        return None
    driver_laps = sorted(
        (lap for lap in laps if lap.get("driver_number") == number and lap.get("date_start")),
        key=lambda lap: lap["date_start"],
    )
    found = None
    for lap in driver_laps:
        start = _parse(lap["date_start"])
        if start is not None and start <= moment:
            found = lap.get("lap_number")
    return found if isinstance(found, int) else None


def _rounds(meetings: list[dict], sessions: list[dict]) -> list[dict]:
    race_by_meeting = {
        session["meeting_key"]: session
        for session in sessions
        if session.get("session_name") == "Race" and session.get("meeting_key") is not None
    }
    rows = []
    ordered = sorted(meetings, key=lambda meeting: meeting.get("date_start") or "")
    round_no = 0
    for meeting in ordered:
        race = race_by_meeting.get(meeting.get("meeting_key"))
        if not race:
            continue
        round_no += 1
        rows.append(
            {
                "round": round_no,
                "session_key": race["session_key"],
                "label": f"R{round_no} {meeting.get('location') or meeting.get('meeting_name')}",
            }
        )
    return rows


def _lede(
    meeting: dict,
    session: dict,
    classification: list[dict],
    fastest: dict | None,
    control: list[dict],
    raw_swaps: int,
    on_track: int,
    weather: list[dict],
    quali_result: list[dict],
    by_number: dict[int, dict],
) -> list[str]:
    name = meeting.get("meeting_name") or "this race"
    place = session.get("location") or meeting.get("location") or ""
    lines = []
    winner = next((row for row in classification if row.get("position") == 1), None)
    second = next((row for row in classification if row.get("position") == 2), None)
    if winner:
        gap = ""
        if second and second["gap"] not in {"—", "DNF", "DNS", "DSQ"}:
            gap = f" {second['code']} finished {second['gap']}."
        time = f" The winner's time was {winner['time']}." if winner.get("time") else ""
        where = f" at {place}" if place else ""
        lines.append(f"{winner['name'] or winner['code']} won the {session.get('year')} {name}{where}.{gap}{time}")
    else:
        lines.append(f"The {session.get('year')} {name} does not have a published result yet.")
    pole = next((row for row in quali_result if row.get("position") == 1), None)
    if pole and isinstance(pole.get("driver_number"), int):
        driver = by_number.get(int(pole["driver_number"]))
        times = [value for value in pole.get("duration") or [] if isinstance(value, (int, float))]
        pole_time = format_lap(times[-1]) if times else ""
        who = format_name((driver or {}).get("full_name")) or (driver or {}).get("name_acronym") or str(pole["driver_number"])
        lines.append(f"{who} took pole{f' in {pole_time}' if pole_time != '—' else ''}. Qualifying position is not the penalty-adjusted grid.")
    if fastest:
        lines.append(f"Fastest lap was {fastest['code']} on lap {fastest['lap']} in {fastest['time']}.")
    notes = []
    if any("SAFETY CAR" in str(row.get("message") or "").upper() for row in control):
        notes.append("a safety car")
    if any("VIRTUAL SAFETY CAR" in str(row.get("message") or "").upper() or str(row.get("message") or "").upper().startswith("VSC") for row in control):
        notes.append("a virtual safety car")
    if any(str(row.get("flag") or "").upper() == "RED" or "RED FLAG" in str(row.get("message") or "").upper() for row in control):
        notes.append("a red flag")
    if notes:
        lines.append(f"Race control records {', '.join(notes)}.")
    if raw_swaps:
        lines.append(
            f"The overtake feed has {raw_swaps} position swaps. f1-debrief keeps {on_track} after dropping pit stops and penalty messages."
        )
    if weather:
        first = min(weather, key=lambda row: row.get("date") or "")
        air = first.get("air_temperature")
        track = first.get("track_temperature")
        if isinstance(air, (int, float)) and isinstance(track, (int, float)):
            rain = " Rain was recorded." if any(
                isinstance(row.get("rainfall"), (int, float)) and row["rainfall"] > 0 for row in weather
            ) else " No rainfall was recorded."
            lines.append(f"Air {air:.0f}°C, track {track:.0f}°C at the first weather sample.{rain}")
    return lines


def _tone(flag: str, message: str) -> str:
    text = f"{flag} {message}".upper()
    if "RED" in text:
        return "red"
    if "SAFETY CAR" in text or "VSC" in text or "VIRTUAL SAFETY" in text:
        return "sc"
    if "YELLOW" in text:
        return "yellow"
    if "GREEN" in text or "CHEQUERED" in text:
        return "green"
    if "PENALTY" in text:
        return "penalty"
    return ""


def _seconds(value: object) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "—"
    return f"{value:.1f}"


def _sector(value: object) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "—"
    return f"{value:.3f}"


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
