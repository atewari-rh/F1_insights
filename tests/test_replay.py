from datetime import datetime, timedelta, timezone

from f1insights.replay import attach_telemetry, build_replay, compact_car, enrich_replay, mark_drs


def test_replay_scales_and_downsamples() -> None:
    drivers = [
        {"driver_number": 4, "name_acronym": "NOR", "team_colour": "FF8000"},
        {"driver_number": 1, "name_acronym": "VER", "team_colour": "3671C6"},
    ]
    locations = []
    for index in range(11):
        moment = f"2024-09-01T13:00:{index:02d}+00:00"
        locations.append({"driver_number": 4, "date": moment, "x": 1000 + index * 10, "y": 2000, "z": 0})
        locations.append({"driver_number": 1, "date": moment, "x": 0, "y": 0, "z": 0})
        locations.append({"driver_number": 1, "date": moment, "x": 5000, "y": 4000 + index, "z": 1})
    document = build_replay(locations, drivers, step_s=2.0)

    assert document["duration_s"] == 10.0
    norris = next(car for car in document["cars"] if car["code"] == "NOR")
    assert norris["samples"][0]["x"] == 100.0
    assert norris["samples"][0]["y"] == 200.0
    assert len(norris["samples"]) == 6
    assert norris["colour"] == "FF8000"
    assert document["track"]
<<<<<<< Updated upstream
=======
    assert document["track_width_m"] == 14


def test_replay_track_is_one_closed_lap() -> None:
    drivers = [{"driver_number": 4, "name_acronym": "NOR", "team_colour": "FF8000"}]
    locations = []
    side = 8000
    step = 200
    x = y = 0
    second = 0
    edges = ((step, 0), (0, step), (-step, 0), (0, -step))
    for _lap in range(2):
        for dx, dy in edges:
            for _ in range(side // step):
                x += dx
                y += dy
                locations.append(
                    {
                        "driver_number": 4,
                        "date": f"2024-09-01T13:{second // 60:02d}:{second % 60:02d}+00:00",
                        "x": x,
                        "y": y,
                        "z": 0,
                    }
                )
                second += 1
    locations.append(
        {
            "driver_number": 4,
            "date": f"2024-09-01T13:{second // 60:02d}:{second % 60:02d}+00:00",
            "x": 500000,
            "y": 500000,
            "z": 0,
        }
    )
    document = build_replay(locations, drivers, step_s=2.0)
    track = document["track"]

    assert track[0] == track[-1]
    xs = [point[0] for point in track]
    ys = [point[1] for point in track]
    assert max(xs) - min(xs) == 800
    assert max(ys) - min(ys) == 800
    assert max(xs) < 1000


def test_drs_marks_the_open_stretch() -> None:
    start = datetime(2024, 5, 26, 14, 0, tzinfo=timezone.utc)
    track = [[float(index * 10), 0.0] for index in range(40)]
    located = []
    rows = []
    for lap in range(3):
        for index in range(40):
            moment = start + timedelta(seconds=lap * 50 + index)
            along = index * 10.0
            located.append((moment, along, 0.0))
            rows.append({"date": moment.isoformat(), "drs": 12 if along >= 200 else 1})
    mask = mark_drs(track, located, rows)

    assert mask[5] == 0
    assert mask[30] == 1
    assert sum(mask) >= 8


def test_enrich_adds_order_weather_and_clock() -> None:
    drivers = [{"driver_number": 4, "name_acronym": "NOR", "team_colour": "FF8000"}]
    locations = [
        {"driver_number": 4, "date": f"2024-09-01T13:00:{index:02d}+00:00", "x": 1000 + index, "y": 2000, "z": 0}
        for index in range(6)
    ]
    document = build_replay(locations, drivers, step_s=1)
    enrich_replay(
        document,
        locations=locations,
        car_rows=[],
        positions=[
            {"driver_number": 4, "date": "2024-09-01T12:30:00+00:00", "position": 3},
            {"driver_number": 4, "date": "2024-09-01T13:00:02+00:00", "position": 2},
            {"driver_number": 4, "date": "2024-09-01T13:00:04+00:00", "position": 1},
        ],
        laps=[{"driver_number": 4, "lap_number": 1, "date_start": "2024-09-01T13:00:01+00:00"}],
        weather=[
            {
                "date": "2024-09-01T13:00:03+00:00",
                "air_temperature": 21.1,
                "track_temperature": 40,
                "humidity": 60,
                "wind_speed": 1.2,
                "wind_direction": 180,
                "rainfall": 0,
            }
        ],
        driver_number=4,
    )

    assert document["view"] == 5
    assert document["race_start_s"] == 1.0
    assert document["lap_total"] == 1
    assert document["cars"][0]["number"] == 4
    assert document["cars"][0]["places"] == [{"t": 0.0, "p": 3}, {"t": 2.0, "p": 2}, {"t": 4.0, "p": 1}]
    assert document["cars"][0]["laps"] == [{"t": 1.0, "n": 1}]
    assert document["weather"][0]["wind_from"] == "S"
    assert not any(document["drs"])


def test_attach_telemetry_holds_a_fresh_reading() -> None:
    drivers = [{"driver_number": 4, "name_acronym": "NOR", "team_colour": "FF8000"}]
    locations = [
        {"driver_number": 4, "date": "2024-09-01T13:00:00+00:00", "x": 1000, "y": 2000, "z": 0},
        {"driver_number": 4, "date": "2024-09-01T13:00:02+00:00", "x": 1100, "y": 2000, "z": 0},
    ]
    document = build_replay(locations, drivers, step_s=1)
    series = compact_car(
        [
            {
                "date": "2024-09-01T13:00:00+00:00",
                "speed": 210,
                "n_gear": 6,
                "throttle": 80,
                "brake": False,
                "drs": 12,
            },
            {
                "date": "2024-09-01T13:00:02+00:00",
                "speed": 180,
                "n_gear": 5,
                "throttle": 104,
                "brake": 100,
                "drs": 0,
            },
        ]
    )
    attach_telemetry(document, {4: series}, locations)
    first = document["cars"][0]["samples"][0]
    second = document["cars"][0]["samples"][1]

    assert first["speed"] == 210
    assert first["gear"] == 6
    assert first["throttle"] == 80
    assert first["brake"] == 0
    assert first["drs"] == 1
    assert second["throttle"] == 80
    assert second["brake"] == 100
    assert second["drs"] == 0
>>>>>>> Stashed changes
