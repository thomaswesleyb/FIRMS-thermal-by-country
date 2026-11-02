"""Download FIRMS yearly per-country archive CSVs (MODIS, VIIRS S-NPP, VIIRS NOAA-20).

These public files need no MAP_KEY, contain standard-processing data once finalised, and
include the `type` column (0 vegetation, 1 volcano, 2 other static land source, 3 offshore).
URL pattern, verified 2026-11-02:
    {base}/{product}/{year}/{product}_{year}_{Country}.csv
"""

from dataclasses import dataclass, field
from pathlib import Path

import httpx

from firms_monitor.config import Config
from firms_monitor.firms.cache import fetch_csv, is_cached


@dataclass
class ArchiveReport:
    """Archive files fetched, reused from cache, or absent on the server (404)."""

    country: str
    downloaded: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def archive_url(base_url: str, product: str, year: int, country: str) -> str:
    """URL of one yearly country archive file."""
    return f"{base_url}/{product}/{year}/{product}_{year}_{country}.csv"


def archive_path(raw_dir: Path, product: str, year: int, country: str) -> Path:
    """Local cache path of one yearly country archive file."""
    return raw_dir / "firms" / "country_archive" / product / f"{product}_{year}_{country}.csv"


def download_country_archive(client: httpx.Client, config: Config, country: str) -> ArchiveReport:
    """Fetch every configured product-year for `country`, skipping cached files.

    A 404 for a single product-year is recorded in `missing` (e.g. a year not yet
    published) rather than raised.

    Raises:
        ValueError: If no file at all exists for `country`, which almost always means the
            country name is misspelled (FIRMS uses names like "United_Kingdom").
    """
    report = ArchiveReport(country=country)
    for product in config.firms.archive_products:
        for year in range(config.start.year, config.end.year + 1):
            dest = archive_path(config.paths.raw, product, year, country)
            label = dest.name
            if is_cached(dest):
                report.cached.append(label)
                continue
            url = archive_url(config.firms.archive_base_url, product, year, country)
            if fetch_csv(client, url, dest, public_url=url):
                report.downloaded.append(label)
            else:
                report.missing.append(label)
    if not (report.downloaded or report.cached):
        raise ValueError(
            f"No FIRMS country-archive files found for {country!r}. Check the spelling "
            f"against {config.firms.archive_base_url} (e.g. 'United_Kingdom')."
        )
    return report
