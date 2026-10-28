from datetime import datetime

from f1insights.dossier import assemble


def test_assemble_keeps_the_race_and_drops_a_pit_swap() -> None:
    drivers = [
        {
            "driver_number": 4,
            "name_acronym": "NOR",
            "full_name": "Lando NORRIS",
            "team_name": "McLaren",
            "team_colour": "FF8000",
        },
        {
            "driver_number": 1,
            "name_acronym": "VER",
            "full_name": "Max Verstappen",
            "team_name": "Red Bull Racing",
            "team_colour": "3671C6",
        },
    ]
    session = {
        "session_key": 1,
        "year": 2024,
        "meeting_key": 10,
        "gmt_offset": "02:00:00",
        "date_start": "2024-09-01T13:00:00+00:00",
        "location": "Monza",
        "country_name": "Italy",
        "session_name": "Race",
    }
    meeting = {
        "meeting_key": 10,
        "meeting_name": "Italian Grand Prix",
        "location": "Monza",
        "country_name": "Italy",
        "date_start": "2024-08-30T00:00:00+00:00",
        "gmt_offset": "02:00:00",
    }
    result = [
        {
            "position": 1,
            "driver_number": 4,
            "number_of_laps": 53,
            "points": 25,
            "duration": 4480.727,
            "gap_to_leader": 0,
            "dnf": False,
        },
        {
            "position": 2,
            "driver_number": 1,
            "number_of_laps": 53,
            "points": 18,
            "duration": 4483.391,
            "gap_to_leader": 2.664,
            "dnf": False,
        },
        {
            "position": 15,
            "driver_number": 10,
            "number_of_laps": 2,
            "points": 0,
            "duration": None,
            "gap_to_leader": "+1 LAP",
            "dnf": False,
        },
        {
            "position": None,
            "driver_number": 22,
            "number_of_laps": 7,
            "points": 0,
            "dnf": True,
            "gap_to_leader": None,
        },
    ]
    laps = [
        {
            "driver_number": 4,
            "lap_number": 41,
            "date_start": "2024-09-01T14:09:00+00:00",
            "lap_duration": 82.234,
            "duration_sector_1": 26.1,
            "duration_sector_2": 28.2,
            "duration_sector_3": 27.9,
            "st_speed": 340,
            "i1_speed": 280,
            "i2_speed": 290,
            "is_pit_out_lap": False,
        },
        {
            "driver_number": 1,
            "lap_number": 41,
            "date_start": "2024-09-01T14:09:02+00:00",
            "lap_duration": 88.738,
            "duration_sector_1": 27.0,
            "duration_sector_2": 30.0,
            "duration_sector_3": 31.0,
            "st_speed": 330,
            "is_pit_out_lap": False,
        },
        {"driver_number": 10, "lap_number": 1, "date_start": "2024-09-01T13:01:00+00:00", "lap_duration": 40.0, "is_pit_out_lap": False},
        {"driver_number": 10, "lap_number": 2, "date_start": "2024-09-01T13:01:40+00:00", "lap_duration": 41.0, "is_pit_out_lap": False},
    ]
    overtakes = [
        {
            "date": "2024-09-01T14:00:00+00:00",
            "overtaking_driver_number": 4,
            "overtaken_driver_number": 1,
            "position": 3,
        },
        {
            "date": "2024-09-01T14:10:00+00:00",
            "overtaking_driver_number": 4,
            "overtaken_driver_number": 1,
            "position": 2,
        },
    ]
    pits = [
        {
            "date": "2024-09-01T14:00:10+00:00",
            "driver_number": 1,
            "lap_number": 20,
            "pit_duration": 25.0,
            "stop_duration": 2.4,
            "lane_duration": 22.0,
        }
    ]
    control = [
        {
            "date": "2024-09-01T13:20:00+00:00",
            "lap_number": 12,
            "category": "Flag",
            "flag": "RED",
            "message": "RED FLAG",
            "driver_number": None,
        }
    ]
    dossier = assemble(
        meeting=meeting,
        session=session,
        weekend=[{"session_name": "Qualifying", "session_key": 2, "meeting_key": 10}],
        drivers=drivers,
        result=result,
        quali_result=[{"position": 1, "driver_number": 4, "duration": [79.911, 79.727, 79.327]}],
        laps=laps,
        pits=pits,
        stints=[{"driver_number": 4, "stint_number": 1, "lap_start": 1, "lap_end": 41, "compound": "MEDIUM"}],
        weather=[{"date": "2024-09-01T11:00:00+00:00", "air_temperature": 26, "track_temperature": 42, "humidity": 40, "wind_speed": 1.2, "rainfall": 0}],
        control=control,
        overtakes=overtakes,
        positions=[
            {"date": "2024-09-01T14:08:00+00:00", "driver_number": 4, "position": 2},
            {"date": "2024-09-01T14:08:00+00:00", "driver_number": 1, "position": 3},
        ],
        year_meetings=[meeting],
        year_sessions=[session],
    )

    assert dossier["recorded_pair"] is False
    assert dossier["classification"][0]["code"] == "NOR"
    assert dossier["classification"][0]["name"] == "Lando Norris"
    assert dossier["classification"][0]["gap"] == "Leader"
    assert dossier["classification"][0]["time"].startswith("1:")
    assert dossier["classification"][1]["gap"] == "+2.664"
    assert dossier["classification"][1]["time"] == "1:14:43.391"
    lapped = next(row for row in dossier["classification"] if row["code"] == "10")
    assert lapped["gap"] == "+1 LAP"
    assert lapped["time"] == "1:21.000"
    assert dossier["classification"][1]["grid"] is None
    assert dossier["classification"][0]["grid"] == 1
    assert next(row for row in dossier["classification"] if row["gap"] == "DNF")["time"] == "—"
    assert dossier["raw_swaps"] == 2
    assert dossier["on_track"] == 1
    assert dossier["passes"][0]["overtaking"] == "NOR"
    assert dossier["passes"][0]["index"] == 0
    assert dossier["passes"][0]["lap"] == 41
    assert any("Qualifying position is not the penalty-adjusted grid." in card["text"] for card in dossier["lede"])
    assert any("red flag" in card["text"] for card in dossier["lede"])
    assert dossier["fastest"]["code"] == "NOR"
    assert dossier["chart"]["laps"] == [1] or 41 in dossier["chart"]["laps"]
    assert dossier["stints"][0]["stints"][0]["compound"] == "MEDIUM"
    assert dossier["control"][0]["tone"] == "red"
    assert dossier["time_label"] == "UTC+2"
    assert datetime.fromisoformat(overtakes[1]["date"])
