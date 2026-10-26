import json
from io import BytesIO
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from f1insights import source, web


def test_round_numbers_skip_testing() -> None:
    from f1insights.season import build_board

    meetings = [
        {"meeting_key": 1, "meeting_name": "Pre-Season Testing", "date_start": "2024-02-21T00:00:00+00:00", "location": "Sakhir"},
        {"meeting_key": 2, "meeting_name": "Bahrain Grand Prix", "date_start": "2024-02-29T00:00:00+00:00", "location": "Sakhir"},
    ]
    sessions = [
        {"meeting_key": 1, "session_key": 10, "session_name": "Practice 1"},
        {"meeting_key": 2, "session_key": 20, "session_name": "Race"},
    ]
    document = build_board(2024, meetings, sessions, {20: [{"position": 1, "driver_number": 1, "points": 25}]}, {20: [{"driver_number": 1, "name_acronym": "VER", "full_name": "Max VERSTAPPEN", "team_name": "Red Bull Racing", "team_colour": "3671C6"}]})
    assert document["meetings"][0]["round"] is None
    assert document["meetings"][1]["round"] == 1
    assert document["meetings"][1]["winner_name"] == "Max Verstappen"


def test_season_and_race_render(monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "board",
        lambda year: {
            "year": year,
            "meetings": [
                {
                    "round": 16,
                    "name": "Italian Grand Prix",
                    "location": "Monza",
                    "country": "Italy",
                    "when": "1 Sep 2024",
                    "cancelled": False,
                    "session_key": 9590,
                    "winner": "LEC",
                    "winner_name": "Charles Leclerc",
                    "colour": "E80020",
                    "sprint": None,
                    "image": "",
                }
            ],
            "drivers": [
                {
                    "position": 1,
                    "code": "VER",
                    "name": "Max Verstappen",
                    "colour": "3671C6",
                    "points_label": "437",
                    "wins": 9,
                    "starts": 16,
                }
            ],
            "teams": [
                {"position": 1, "team": "McLaren", "colour": "FF8000", "points_label": "516", "wins": 4}
            ],
            "points_note": "Points are the sum of the race and sprint results OpenF1 published for this season.",
        },
    )
    monkeypatch.setattr(
        web,
        "load_race",
        lambda session_key: {
            "session_key": session_key,
            "year": 2024,
            "name": "Italian Grand Prix",
            "official_name": "Formula 1 Pirelli Gran Premio d'Italia 2024",
            "location": "Monza",
            "country": "Italy",
            "date_label": "1 Sep 2024",
            "time_label": "UTC+2",
            "cancelled": False,
            "lede": ["Charles Leclerc won the 2024 Italian Grand Prix at Monza."],
            "warnings": [],
            "classification": [
                {
                    "position": 1,
                    "code": "LEC",
                    "name": "Charles Leclerc",
                    "team": "Ferrari",
                    "colour": "E80020",
                    "grid": 4,
                    "laps": 53,
                    "gap": "Leader",
                    "time": "1:14:40.727",
                    "points": "25",
                }
            ],
            "qualifying": [],
            "fastest": None,
            "sectors": [],
            "traps": [],
            "chart": {"laps": [], "series": []},
            "stints": [],
            "passes": [
                {"time": "16:00:37", "overtaking": "NOR", "overtaken": "VER", "position": 4, "index": 0, "lap": 41}
            ],
            "raw_swaps": 2,
            "on_track": 1,
            "pits": [],
            "control": [],
            "weather": None,
            "drivers_detail": [],
            "rounds": [{"round": 16, "session_key": 9590, "label": "R16 Monza"}],
            "recorded_pair": True,
        },
    )

    client = TestClient(web.app)
    season = client.get("/?year=2024")
    assert season.status_code == 200
    assert "Charles Leclerc" in season.text
    assert "/race/9590" in season.text

    race = client.get("/race/9590")
    assert race.status_code == 200
    assert "1:14:40.727" in race.text
    assert "/race/9590/pass/NOR/VER/0" in race.text
    assert "recorded f1-debrief card" in race.text


def test_fetch_retries_a_rate_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(source, "_CACHE", tmp_path)
    monkeypatch.setattr(source, "_pace", lambda: None)
    monkeypatch.setattr(source, "_retry_wait", lambda exc, attempt: 0)
    calls = {"n": 0}

    class Body:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'[{"session_key": 1}]'

    def fake_urlopen(request, timeout=90):
        calls["n"] += 1
        if calls["n"] < 3:
            raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))
        return Body()

    monkeypatch.setattr(source, "urlopen", fake_urlopen)
    rows = source.fetch("sessions", session_key=1)
    assert rows == [{"session_key": 1}]
    assert calls["n"] == 3
    cached = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert cached["data"] == rows


def test_recorded_pass_page(monkeypatch) -> None:
    monkeypatch.setattr("f1insights.cards._colours", lambda session_key: {"NOR": "FF8000", "VER": "3671C6"})
    client = TestClient(web.app)
    page = client.get("/race/9590/pass/NOR/VER/0")
    assert page.status_code == 200
    assert "730" in page.text
    assert "750" in page.text
    assert "224" in page.text
    assert "on the inside" in page.text
