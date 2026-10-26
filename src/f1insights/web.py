"""The season dossier. Open a race you missed."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from f1debrief.openf1 import DebriefError
from f1frame import F1FrameError
from f1insights.cards import load_card
from f1insights.dossier import load_race
from f1insights.replay import (
    attach_telemetry,
    build_replay,
    busiest_driver,
    compact_car,
    drivers_by_laps,
    enrich_replay,
    has_open_drs,
)
from f1insights.season import board
from f1insights.source import SourceError, cache_directory, cache_max_age, fetch

ROOT = Path(__file__).resolve().parent
YEARS = (2023, 2024, 2025, 2026)

app = FastAPI(title="F1 Insights")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


@app.get("/", response_class=HTMLResponse)
def season(request: Request, year: int = 2026) -> HTMLResponse:
    if year not in YEARS:
        year = 2026
    try:
        standings = board(year)
    except SourceError as exc:
        return _error(request, str(exc), year)
    return templates.TemplateResponse(
        request,
        "season.html",
        {"board": standings, "years": YEARS, "year": year},
    )


@app.get("/race/{session_key}", response_class=HTMLResponse)
def race(request: Request, session_key: int) -> HTMLResponse:
    try:
        dossier = load_race(session_key)
    except SourceError as exc:
        return _error(request, str(exc), 2026)
    return templates.TemplateResponse(
        request,
        "race.html",
        {"race": dossier, "years": YEARS, "year": dossier["year"]},
    )


@app.get("/race/{session_key}/pass/{first}/{second}/{index}", response_class=HTMLResponse)
def approach(request: Request, session_key: int, first: str, second: str, index: int) -> HTMLResponse:
    try:
        card = load_card(session_key, first, second, index)
    except (DebriefError, SourceError, F1FrameError) as exc:
        return _error(request, str(exc), 2026, status=404)
    return templates.TemplateResponse(
        request,
        "pass.html",
        {"card": card, "session_key": session_key, "years": YEARS, "year": card.get("year") or 2026},
    )


@app.get("/api/race/{session_key}/replay")
def replay(session_key: int) -> dict:
    try:
        return load_replay(session_key)
    except SourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def load_replay(session_key: int) -> dict:
    sessions = fetch("sessions", session_key=session_key)
    if not sessions:
        raise SourceError(f"No session {session_key}")
    session = sessions[0]
    age = cache_max_age(session.get("date_end"))
    path = cache_directory() / f"replay-{session_key}.json"
    cached = _compiled(path, age)
<<<<<<< Updated upstream
    if cached is not None:
=======
    if cached is not None and cached.get("view") == 5:
>>>>>>> Stashed changes
        return cached
    drivers = fetch("drivers", max_age_s=age, session_key=session_key)
    lap_rows = fetch("laps", max_age_s=age, session_key=session_key)
    rank = {number: index for index, number in enumerate(drivers_by_laps(lap_rows))}

    def one(driver: dict) -> tuple:
        number = driver.get("driver_number")
        if not isinstance(number, int):
            return None, [], []
        return (
            number,
            fetch("location", max_age_s=age, session_key=session_key, driver_number=number),
            fetch("car_data", max_age_s=age, session_key=session_key, driver_number=number),
        )

    locations: list = []
    series: dict[int, list] = {}
    reference: int | None = None
    car_rows: list = []
    reference_rank = 10**9
    reference_open = False
    with ThreadPoolExecutor(max_workers=6) as pool:
        for number, located, raw in pool.map(one, drivers):
            if number is None:
                continue
            locations.extend(located)
            series[number] = compact_car(raw)
            place = rank.get(number, 10**6)
            opens = has_open_drs(raw)
            if opens and (not reference_open or place < reference_rank):
                reference, car_rows, reference_rank, reference_open = number, raw, place, True
            elif not reference_open and place < reference_rank:
                reference, car_rows, reference_rank = number, raw, place
    if reference is None:
        reference = busiest_driver(locations)
    document = build_replay(locations, drivers)
    attach_telemetry(document, series, locations)
    enrich_replay(
        document,
        locations=locations,
        car_rows=car_rows,
        positions=fetch("position", max_age_s=age, session_key=session_key),
        laps=lap_rows,
        weather=fetch("weather", max_age_s=age, session_key=session_key),
        driver_number=reference,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def _compiled(path: Path, max_age_s: float | None) -> dict | None:
    if not path.is_file():
        return None
    if max_age_s is not None and __import__("time").time() - path.stat().st_mtime > max_age_s:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _error(request: Request, message: str, year: int, status: int = 502) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "error.html",
        {"message": message, "years": YEARS, "year": year},
        status_code=status,
    )


def main() -> None:
    import uvicorn

    uvicorn.run("f1insights.web:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
