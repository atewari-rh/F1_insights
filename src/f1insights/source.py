"""OpenF1 reads with a disk cache.

Historical sessions are safe to keep. A session that ended recently is
refreshed, so a race that is still being classified does not stick.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger("f1insights")

_BASE = "https://api.openf1.org/v1"
_CACHE = Path(__file__).resolve().parents[2] / "cache"
_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()
_PACE = threading.Lock()
_NEXT = 0.0
_INTERVAL_S = 0.3


class SourceError(Exception):
    """The timing feed could not be read."""


def fetch(path: str, *, max_age_s: float | None = None, **params) -> list:
    """Return one OpenF1 collection. A 404 is an empty list."""

    query = urlencode(sorted((key, value) for key, value in params.items() if value is not None))
    url = f"{_BASE}/{path}?{query}" if query else f"{_BASE}/{path}"
    path_on_disk = _CACHE / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.json"
    with _lock(url):
        cached = _read(path_on_disk, max_age_s)
        if cached is not None:
            return cached
        log.info("OpenF1 %s", url)
        payload = _download(url, path)
        if isinstance(payload, dict):
            raise SourceError(f"OpenF1 {path} returned an error: {payload}")
        _CACHE.mkdir(parents=True, exist_ok=True)
        path_on_disk.write_text(json.dumps({"url": url, "data": payload}), encoding="utf-8")
        return payload


def _download(url: str, path: str) -> list | dict:
    last: Exception | None = None
    for attempt in range(8):
        _pace()
        request = Request(url, headers={"User-Agent": "f1-insights", "Accept": "application/json"})
        try:
            with urlopen(request, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            exc.read()
            if exc.code == 404:
                return []
            last = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt < 7:
                time.sleep(_retry_wait(exc, attempt))
                continue
            raise SourceError(f"OpenF1 {path} returned {exc.code}") from exc
        except URLError as exc:
            last = exc
            if attempt < 3:
                time.sleep(1.0 + attempt)
                continue
            raise SourceError(f"OpenF1 {path} could not be reached ({exc.reason})") from exc
        except json.JSONDecodeError as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.0)
                continue
            raise SourceError(f"OpenF1 {path} returned unreadable JSON") from exc
    raise SourceError(f"OpenF1 {path} could not be reached") from last


def _pace() -> None:
    global _NEXT
    with _PACE:
        now = time.monotonic()
        wait = _NEXT - now
        _NEXT = max(now, _NEXT) + _INTERVAL_S
    if wait > 0:
        time.sleep(wait)


def _retry_wait(exc: HTTPError, attempt: int) -> float:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header and header.replace(".", "", 1).isdigit():
        return min(float(header), 30.0)
    return min(2.0 * (attempt + 1), 20.0)


def cache_directory() -> Path:
    return _CACHE


def cache_max_age(date_end: str | None, now: datetime | None = None) -> float | None:
    """Keep a finished session. Recheck one that ended in the last two days."""

    moment = _parse(date_end)
    if moment is None:
        return 3600
    current = now or datetime.now(timezone.utc)
    if moment < current - timedelta(days=2):
        return None
    return 3600


def _lock(url: str) -> threading.Lock:
    with _GUARD:
        lock = _LOCKS.get(url)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[url] = lock
        return lock


def _read(path: Path, max_age_s: float | None) -> list | None:
    if not path.is_file():
        return None
    if max_age_s is not None and time.time() - path.stat().st_mtime > max_age_s:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    return data


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
