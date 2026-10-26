# F1 Insights

A season dossier for a race you missed. Open a round and the page has the classification, qualifying, every lap, the pits, the tyre stints, the weather samples, and the race-control log. On-track passes open as an f1-debrief approach card: both laps on one shared meter grid, the corner the map chose, the brake meters, and how far the speed integral misses the official lap-time gap.

The track drawing is the same idea as a race replay: scrub the location stream and watch the order change. It uses the public timing map, one path per car. It does not invent a safety-car position, and it does not say who was on the inside.

## Install

This app reads `f1frame` and `f1-debrief` from the library next to it. That library is not on PyPI. Install it from its repository, then this one:

```bash
pip install -e /path/to/f1_debrief
pip install -e ".[dev]"
f1-insights
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Python 3.11 or newer. Historical pages come from OpenF1 and are cached under `cache/`.

## What a race page contains

- The winner, the gap to second, the winner's time, pole, the fastest lap, and whether race control called a safety car, a virtual safety car, or a red flag.
- Classification, with the qualifying order in its own column. That column is qualifying, not the penalty-adjusted grid.
- Qualifying, best sectors, and the highest speed-trap readings.
- Position at the start of each lap.
- A replay of the location stream, loaded when you ask for it. The first load for a race downloads every car. The drawing is kept in `cache/replay-<session>.json`.
- Tyre stints, every pit stop, and every race-control message.
- Every lap for every driver: time, three sectors, and the three speed traps.
- On-track passes. `f1-debrief` drops pit-lane swaps and swaps next to a penalty message. Each remaining pass links to the approach card, and the index is the same index `card_from_race` uses.

## The recorded card

The 2024 Italian Grand Prix is OpenF1 session `9590`. Norris passing Verstappen on lap 41 is the pass stored in the f1-debrief fixture. That card opens from the fixture, so the page does not download the two laps again. The race page links it directly: `/race/9590/pass/NOR/VER/0`.

Any other pass calls `payload_from_race`, then `align_laps` once, then the same card.

## Tests

```bash
pytest
```

The suite builds a race in memory, checks that a pit-adjacent swap is dropped, downsamples a location stream, and renders the recorded Monza card. It does not call OpenF1.
