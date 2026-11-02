"""Download FIRMS detections by bounding box through the Area API (needs FIRMS_MAP_KEY).

Used for products missing from the country archive (VIIRS NOAA-21). Endpoints and
limits, verified 2026-11-02 at https://firms.modaps.eosdis.nasa.gov/api/ :
    /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}/{YYYY-MM-DD}
        DAY_RANGE is 1..5; returns DATE .. DATE + DAY_RANGE - 1.
    /api/data_availability/csv/{MAP_KEY}/{SOURCE}  ->  data_id,min_date,max_date
    /mapserver/mapkey_status/?MAP_KEY=...  ->  JSON with transaction_limit
    Limit: 5000 transactions per 10 minutes; multi-day requests can count as several.
Area API rows have no `type` column.
"""

import csv
import datetime as dt
import io
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from firms_monitor.config import Config
from firms_monitor.firms.cache import FirmsResponseError, fetch_csv, is_cached

REDACTED = "<MAP_KEY>"


@dataclass
class ApiReport:
    """Outcome of one Area API download: chunk counts and uncovered date spans."""

    country: str
    source: str
    downloaded: int = 0
    cached: int = 0
    gaps: list[str] = field(default_factory=list)


def date_chunks(start: dt.date, end: dt.date, max_days: int) -> list[tuple[dt.date, int]]:
    """Split the inclusive range [start, end] into (chunk_start, n_days) pieces."""
    chunks = []
    cursor = start
    while cursor <= end:
        days = min(max_days, (end - cursor).days + 1)
        chunks.append((cursor, days))
        cursor += dt.timedelta(days=days)
    return chunks


def api_chunk_path(raw_dir: Path, source: str, country: str, start: dt.date, days: int) -> Path:
    """Local cache path of one Area API request."""
    return raw_dir / "firms" / "area_api" / source / country / f"{start.isoformat()}_{days}d.csv"


def check_map_key(client: httpx.Client, base_url: str, map_key: str) -> dict[str, object]:
    """Return the MAP_KEY status JSON, or raise if FIRMS does not accept the key."""
    response = client.get(f"{base_url}/mapserver/mapkey_status/", params={"MAP_KEY": map_key})
    try:
        status = response.json()
    except ValueError:
        status = None
    if not isinstance(status, dict) or "transaction_limit" not in status:
        raise FirmsResponseError(
            f"FIRMS rejected FIRMS_MAP_KEY ({response.text[:100]!r}). Request a key at "
            f"{base_url}/api/map_key/ and put it in .env."
        )
    return status


def data_availability(
    client: httpx.Client, base_url: str, map_key: str, source: str
) -> tuple[dt.date, dt.date] | None:
    """Return the (min_date, max_date) FIRMS holds for `source`, or None if not listed."""
    response = client.get(f"{base_url}/api/data_availability/csv/{map_key}/{source}")
    if response.status_code != 200 or not response.text.startswith("data_id"):
        raise FirmsResponseError(
            f"Unexpected data_availability response for {source} "
            f"(HTTP {response.status_code}): {response.text[:200]!r}"
        )
    for row in csv.DictReader(io.StringIO(response.text)):
        if row["data_id"] == source:
            return dt.date.fromisoformat(row["min_date"]), dt.date.fromisoformat(row["max_date"])
    return None


def download_area(
    client: httpx.Client,
    config: Config,
    country: str,
    source: str,
    map_key: str,
) -> ApiReport:
    """Fetch `source` over the country's bounding box for the configured date range.

    The range is clamped to what FIRMS reports as available; anything outside it is
    recorded in `ApiReport.gaps`. Cached chunks are skipped, so reruns resume.

    Raises:
        ValueError: If `country` has no bounding box in config.yaml.
        FirmsResponseError: If FIRMS returns a non-CSV body or 404 for a chunk.
    """
    if country not in config.firms.country_bbox:
        raise ValueError(f"No firms.country_bbox entry for {country!r} in config.yaml")
    bbox = ",".join(str(v) for v in config.firms.country_bbox[country])
    base = config.firms.api_base_url
    report = ApiReport(country=country, source=source)

    available = data_availability(client, base, map_key, source)
    start, end = _clamp(config.start, config.end, available, report.gaps)

    for chunk_start, days in date_chunks(start, end, config.firms.api_max_day_range):
        dest = api_chunk_path(config.paths.raw, source, country, chunk_start, days)
        if is_cached(dest):
            report.cached += 1
            continue
        url = f"{base}/api/area/csv/{map_key}/{source}/{bbox}/{days}/{chunk_start.isoformat()}"
        public_url = url.replace(map_key, REDACTED)
        if not fetch_csv(client, url, dest, public_url=public_url):
            raise FirmsResponseError(f"404 from {public_url}")
        report.downloaded += 1
        time.sleep(config.firms.api_min_request_interval_s)
    return report


def _clamp(
    start: dt.date,
    end: dt.date,
    available: tuple[dt.date, dt.date] | None,
    gaps: list[str],
) -> tuple[dt.date, dt.date]:
    """Intersect [start, end] with `available`, appending uncovered spans to `gaps`."""
    if available is None:
        gaps.append(f"{start}..{end} (source not listed in data_availability)")
        return start, start - dt.timedelta(days=1)
    lo, hi = available
    if start < lo:
        gaps.append(f"{start}..{min(end, lo - dt.timedelta(days=1))} (before {lo})")
    if end > hi:
        gaps.append(f"{max(start, hi + dt.timedelta(days=1))}..{end} (after {hi})")
    return max(start, lo), min(end, hi)
