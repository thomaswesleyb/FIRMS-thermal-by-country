"""Idempotent, atomic download of FIRMS CSV files into a local cache.

Each cached CSV gets a `<name>.meta.json` sidecar recording where it came from. A file
whose sidecar is missing, or which still contains near-real-time (NRT) rows, is treated
as not cached and is fetched again on the next run.
"""

import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import httpx

CSV_HEADER_PREFIX = "latitude,longitude,"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4


class FirmsResponseError(RuntimeError):
    """FIRMS returned something other than a detections CSV."""


def meta_path(csv_path: Path) -> Path:
    """Sidecar metadata path for a cached CSV."""
    return csv_path.with_name(csv_path.name + ".meta.json")


def is_cached(csv_path: Path) -> bool:
    """True if `csv_path` was fully downloaded and holds final (non-NRT) data."""
    sidecar = meta_path(csv_path)
    if not (csv_path.exists() and sidecar.exists()):
        return False
    return not json.loads(sidecar.read_text())["provisional"]


def fetch_csv(client: httpx.Client, url: str, dest: Path, *, public_url: str) -> bool:
    """Download a FIRMS CSV to `dest` atomically and write its metadata sidecar.

    Args:
        client: HTTP client to use.
        url: Request URL (may contain the MAP_KEY).
        dest: Final path of the cached CSV.
        public_url: `url` with any secret redacted; this is what gets logged and stored.

    Returns:
        False if the server answered 404 (no file for this product/period), else True.

    Raises:
        FirmsResponseError: If the body is not a detections CSV (e.g. "Invalid MAP_KEY.").
        httpx.HTTPError: On non-retryable HTTP errors or after retries are exhausted.
    """
    response = _get_with_retry(client, url, public_url)
    if response.status_code == 404:
        return False
    response.raise_for_status()
    body = response.text
    if not body.startswith(CSV_HEADER_PREFIX):
        raise FirmsResponseError(f"Unexpected response from {public_url}: {body[:200]!r}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    partial.write_text(body)
    partial.replace(dest)
    meta_path(dest).write_text(json.dumps(_metadata(body, response, public_url), indent=2))
    return True


def _get_with_retry(client: httpx.Client, url: str, public_url: str) -> httpx.Response:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(url)
        except httpx.TransportError as exc:
            if attempt == MAX_ATTEMPTS:
                raise httpx.TransportError(f"{exc} (GET {public_url})") from exc
        else:
            if response.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                return response
        time.sleep(2**attempt)
    raise AssertionError("unreachable: retry loop always returns or raises")


def _metadata(body: str, response: httpx.Response, public_url: str) -> dict[str, object]:
    lines = body.splitlines()
    header = lines[0].split(",")
    version_col = header.index("version") if "version" in header else None
    provisional = version_col is not None and any(
        "NRT" in line.split(",")[version_col] for line in lines[1:]
    )
    return {
        "url": public_url,
        "downloaded_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "last_modified": response.headers.get("last-modified"),
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
        "n_rows": len(lines) - 1,
        "provisional": provisional,
    }
