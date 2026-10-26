from f1insights.replay import build_replay


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
