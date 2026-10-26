"""Approach cards from f1-debrief, drawn on the shared f1frame grid."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from f1debrief.dossier import render_text
from f1debrief.openf1 import DebriefError, set_cache_directory
from f1debrief.race import card_from_payload, payload_from_session, prepare_payload, recorded_fixture_path
from f1frame import Lap, align_laps
from f1frame.types import CarStream, PositionStream

from f1insights.source import cache_directory, cache_max_age, fetch

set_cache_directory(cache_directory())

RECORDED_SESSION = 9590
RECORDED_PAIR = frozenset({"NOR", "VER"})


def load_card(session_key: int, first: str, second: str, index: int = 0) -> dict:
    pair = {first.upper(), second.upper()}
    if session_key == RECORDED_SESSION and pair == RECORDED_PAIR and index == 0:
        payload = json.loads(recorded_fixture_path().read_text(encoding="utf-8"))
        document = document_from_payload(payload, recorded=True)
        document["colours"] = _colours(session_key)
        _paint(document)
        return document
    sessions = fetch("sessions", session_key=session_key)
    if not sessions:
        raise DebriefError(f"No session {session_key}")
    session = sessions[0]
    path = cache_directory() / f"card-{session_key}-{first.upper()}-{second.upper()}-{index}.json"
    cached = _cached_card(path, cache_max_age(session.get("date_end")))
    if cached is not None:
        return cached
    payload = payload_from_session(session_key, (first, second), index=index)
    document = document_from_payload(payload, recorded=False)
    document["colours"] = _colours(session_key)
    _paint(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def document_from_payload(payload: dict, *, recorded: bool) -> dict:
    payload = prepare_payload(payload)
    card = card_from_payload(payload)
    frames = align_laps(_laps(payload), step_m=10.0)
    reports = []
    traces = []
    for frame in frames:
        report = frame.report
        reports.append(
            {
                "id": frame.lap_id,
                "official_lap_time_s": report.official_lap_time_s,
                "official_label": None if report.official_lap_time_s is None else f"{report.official_lap_time_s:.3f}",
                "timestamp_error_ms": None if report.timestamp_error_ms is None else round(report.timestamp_error_ms),
                "integrated_speed_error_ms": None
                if report.integrated_speed_error_ms is None
                else round(report.integrated_speed_error_ms),
                "reference_length_m": round(report.reference_length_m),
            }
        )
        chosen = (frame.s_m >= card.start_m) & (frame.s_m <= card.end_m)
        speed = []
        for value in frame.speed_kph[chosen]:
            speed.append(None if not np.isfinite(value) else round(float(value), 1))
        traces.append(
            {
                "id": frame.lap_id,
                "s": [round(float(value), 1) for value in frame.s_m[chosen]],
                "speed": speed,
            }
        )
    return {
        "title": card.title,
        "text": render_text(card),
        "start_m": card.start_m,
        "end_m": card.end_m,
        "pass_s_m": card.pass_s_m,
        "closure_error_ms": None if card.closure_error_ms is None else round(card.closure_error_ms),
        "window_delta_s": None if card.window_delta_s is None else round(card.window_delta_s, 2),
        "corner_index": card.corner_index,
        "corner_direction": card.corner_direction,
        "corner_radius_m": None if card.corner_radius_m is None else round(card.corner_radius_m),
        "note": card.note,
        "confidence": {"level": card.confidence.level, "reasons": list(card.confidence.reasons)},
        "drivers": [
            {
                "lap_id": driver.lap_id,
                "brake_m": None if driver.brake_m is None else round(driver.brake_m),
                "apex_speed_kph": None if driver.apex_speed_kph is None else round(driver.apex_speed_kph),
                "apex_s_m": None if driver.apex_s_m is None else round(driver.apex_s_m),
                "colour": "888888",
            }
            for driver in card.drivers
        ],
        "reports": reports,
        "traces": traces,
        "recorded": recorded,
        "year": payload.get("year"),
        "race": payload.get("race"),
        "session_key": payload.get("session_key"),
    }


def _laps(payload: dict) -> list[Lap]:
    event = payload["pass"]
    built = []
    for code in (event["overtaken"], event["overtaking"]):
        lap = payload["laps"][code]
        raw_time = lap.get("lap_time_s")
        built.append(
            Lap(
                CarStream(
                    time_s=np.asarray(lap["t_car"], dtype=np.float64),
                    speed_kph=np.asarray(lap["speed"], dtype=np.float64),
                    throttle_pct=np.asarray(lap["throttle"], dtype=np.float64),
                    brake=np.asarray(lap["brake"], dtype=np.float64),
                    gear=np.asarray(lap["gear"], dtype=np.float64),
                    rpm=np.asarray(lap["rpm"], dtype=np.float64),
                ),
                PositionStream(
                    time_s=np.asarray(lap["t_loc"], dtype=np.float64),
                    x=np.asarray(lap["x"], dtype=np.float64),
                    y=np.asarray(lap["y"], dtype=np.float64),
                ),
                lap_time_s=None if raw_time is None else float(raw_time),
                lap_id=code,
            )
        )
    return built


def _cached_card(path: Path, max_age_s: float | None) -> dict | None:
    if not path.is_file():
        return None
    if max_age_s is not None and time.time() - path.stat().st_mtime > max_age_s:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "title" not in payload:
        return None
    return payload


def _colours(session_key: int) -> dict[str, str]:
    try:
        drivers = fetch("drivers", session_key=session_key)
    except Exception:
        return {}
    return {
        str(driver.get("name_acronym")): str(driver.get("team_colour") or "888888")
        for driver in drivers
        if driver.get("name_acronym")
    }


def _paint(document: dict) -> None:
    colours = document.get("colours") or {}
    for driver in document["drivers"]:
        driver["colour"] = colours.get(driver["lap_id"], driver["colour"])
    for trace in document["traces"]:
        trace["colour"] = colours.get(trace["id"], "888888")
