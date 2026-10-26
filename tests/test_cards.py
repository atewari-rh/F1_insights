import json

from f1debrief.race import recorded_fixture_path

from f1insights.cards import document_from_payload


def test_recorded_monza_card() -> None:
    payload = json.loads(recorded_fixture_path().read_text(encoding="utf-8"))
    document = document_from_payload(payload, recorded=True)

    brakes = {driver["lap_id"]: driver["brake_m"] for driver in document["drivers"]}
    assert brakes["NOR"] == 730
    assert brakes["VER"] == 750
    for driver, report in zip(document["drivers"], document["reports"], strict=True):
        assert driver["lap_id"] == report["id"]
    assert document["closure_error_ms"] == 224
    assert document["corner_index"] == 1
    assert "Lap-time closure" in document["text"]
    assert "on the inside" in document["text"]
    assert document["confidence"]["level"] == "high"
    assert document["recorded"] is True
    assert document["traces"][0]["s"]
    assert document["reports"][0]["reference_length_m"] > 5000
