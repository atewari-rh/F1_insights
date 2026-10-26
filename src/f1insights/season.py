"""A season board: the calendar, the winners, and the points the feed published."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from f1insights.format import Clock, format_name, format_points
from f1insights.source import SourceError, cache_max_age, fetch


def board(year: int) -> dict:
    age = None if year < _current_year() else 3600.0
    meetings = fetch("meetings", max_age_s=age, year=year)
    sessions = fetch("sessions", max_age_s=age, year=year)
    scoring = [session for session in sessions if session.get("session_name") in {"Race", "Sprint"}]
    results, result_notes = _results(scoring)
    drivers, driver_notes = _drivers(scoring, results)
    document = build_board(year, meetings, sessions, results, drivers)
    document["warnings"] = result_notes + driver_notes
    return document


def build_board(
    year: int,
    meetings: list[dict],
    sessions: list[dict],
    results: dict[int, list[dict]],
    drivers: dict[int, list[dict]],
) -> dict:
    by_meeting: dict[int, list[dict]] = defaultdict(list)
    for session in sessions:
        if session.get("meeting_key") is not None:
            by_meeting[int(session["meeting_key"])].append(session)
    cards = []
    driver_points: dict[int, float] = defaultdict(float)
    driver_wins: dict[int, int] = defaultdict(int)
    driver_starts: dict[int, int] = defaultdict(int)
    team_points: dict[str, float] = defaultdict(float)
    team_wins: dict[str, int] = defaultdict(int)
    team_colour: dict[str, str] = {}
    driver_meta: dict[int, dict] = {}

    ordered = sorted(meetings, key=lambda meeting: meeting.get("date_start") or "")
    round_no = 0
    for meeting in ordered:
        weekend = by_meeting.get(int(meeting["meeting_key"]), []) if meeting.get("meeting_key") is not None else []
        race = next((session for session in weekend if session.get("session_name") == "Race"), None)
        sprint = next((session for session in weekend if session.get("session_name") == "Sprint"), None)
        if race is not None:
            round_no += 1
        clock = Clock(meeting.get("gmt_offset"))
        winner = _winner(results.get(race["session_key"], []) if race else [], drivers.get(race["session_key"], []) if race else [])
        sprint_winner = _winner(
            results.get(sprint["session_key"], []) if sprint else [],
            drivers.get(sprint["session_key"], []) if sprint else [],
        )
        cards.append(
            {
                "round": None if race is None else round_no,
                "name": meeting.get("meeting_name") or meeting.get("location") or "Round",
                "location": meeting.get("location") or "",
                "country": meeting.get("country_name") or "",
                "when": clock.date(meeting.get("date_start")),
                "cancelled": bool(meeting.get("is_cancelled")),
                "session_key": None if race is None else race.get("session_key"),
                "winner": None if winner is None else winner["code"],
                "winner_name": None if winner is None else winner["name"],
                "colour": "888888" if winner is None else winner["colour"],
                "sprint": None if sprint_winner is None else sprint_winner["code"],
                "image": meeting.get("circuit_image") or "",
            }
        )
        for session in (race, sprint):
            if session is None:
                continue
            session_drivers = {
                int(driver["driver_number"]): driver
                for driver in drivers.get(session["session_key"], [])
                if driver.get("driver_number") is not None
            }
            is_race = session.get("session_name") == "Race"
            for row in results.get(session["session_key"], []):
                number = row.get("driver_number")
                if not isinstance(number, int):
                    continue
                points = row.get("points")
                if isinstance(points, (int, float)):
                    driver_points[number] += float(points)
                driver_starts[number] += 1
                if is_race and row.get("position") == 1:
                    driver_wins[number] += 1
                driver = session_drivers.get(number)
                if driver:
                    driver_meta[number] = driver
                    team = str(driver.get("team_name") or "")
                    if team:
                        if isinstance(points, (int, float)):
                            team_points[team] += float(points)
                        if is_race and row.get("position") == 1:
                            team_wins[team] += 1
                        team_colour[team] = str(driver.get("team_colour") or team_colour.get(team) or "888888")

    driver_rows = []
    for number, points in driver_points.items():
        driver = driver_meta.get(number, {})
        driver_rows.append(
            {
                "code": driver.get("name_acronym") or str(number),
                "name": format_name(driver.get("full_name")),
                "team": driver.get("team_name") or "",
                "colour": driver.get("team_colour") or "888888",
                "points": points,
                "points_label": format_points(points),
                "wins": driver_wins[number],
                "starts": driver_starts[number],
            }
        )
    driver_rows.sort(key=lambda row: (-row["points"], -row["wins"], row["code"]))
    for position, row in enumerate(driver_rows, start=1):
        row["position"] = position

    team_rows = []
    for team, points in team_points.items():
        team_rows.append(
            {
                "team": team,
                "colour": team_colour.get(team, "888888"),
                "points": points,
                "points_label": format_points(points),
                "wins": team_wins[team],
            }
        )
    team_rows.sort(key=lambda row: (-row["points"], -row["wins"], row["team"]))
    for position, row in enumerate(team_rows, start=1):
        row["position"] = position

    return {
        "year": year,
        "meetings": cards,
        "drivers": driver_rows,
        "teams": team_rows,
        "points_note": "Points are the sum of the race and sprint results OpenF1 published for this season.",
    }


def _results(sessions: list[dict]) -> tuple[dict[int, list[dict]], list[str]]:
    def one(session: dict) -> tuple[int, list[dict], str | None]:
        name = session.get("session_name") or "session"
        try:
            rows = fetch(
                "session_result",
                max_age_s=cache_max_age(session.get("date_end")),
                session_key=session["session_key"],
            )
        except SourceError as exc:
            return int(session["session_key"]), [], f"{name} result {session.get('session_key')} could not be loaded. {exc}"
        return int(session["session_key"]), rows, None

    if not sessions:
        return {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        packed = list(pool.map(one, sessions))
    return {key: rows for key, rows, _note in packed}, [note for _key, _rows, note in packed if note]


def _drivers(sessions: list[dict], results: dict[int, list[dict]]) -> tuple[dict[int, list[dict]], list[str]]:
    needed = [session for session in sessions if results.get(session["session_key"])]

    def one(session: dict) -> tuple[int, list[dict], str | None]:
        try:
            rows = fetch("drivers", max_age_s=cache_max_age(session.get("date_end")), session_key=session["session_key"])
        except SourceError as exc:
            return int(session["session_key"]), [], f"Driver list {session.get('session_key')} could not be loaded. {exc}"
        return int(session["session_key"]), rows, None

    if not needed:
        return {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        packed = list(pool.map(one, needed))
    return {key: rows for key, rows, _note in packed}, [note for _key, _rows, note in packed if note]


def _winner(result: list[dict], drivers: list[dict]) -> dict | None:
    row = next((item for item in result if item.get("position") == 1), None)
    if row is None or not isinstance(row.get("driver_number"), int):
        return None
    driver = next((item for item in drivers if item.get("driver_number") == row["driver_number"]), {})
    return {
        "code": driver.get("name_acronym") or str(row["driver_number"]),
        "name": format_name(driver.get("full_name")),
        "colour": driver.get("team_colour") or "888888",
    }


def _current_year() -> int:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).year
