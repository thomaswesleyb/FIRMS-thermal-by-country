import dataclasses
import datetime as dt
import json

import httpx
import pytest

from firms_monitor.config import Config
from firms_monitor.firms.area_api import (
    api_chunk_path,
    check_map_key,
    date_chunks,
    download_area,
)
from firms_monitor.firms.cache import FirmsResponseError, meta_path
from tests.conftest import API_HEADER

KEY = "abcdef0123456789abcdef0123456789"
D = dt.date


def test_date_chunks_cover_range_without_overlap() -> None:
    chunks = date_chunks(D(2024, 2, 26), D(2024, 3, 6), 5)
    assert chunks == [(D(2024, 2, 26), 5), (D(2024, 3, 2), 5)]


def test_date_chunks_short_final_chunk_and_single_day() -> None:
    assert date_chunks(D(2024, 1, 1), D(2024, 1, 7), 5) == [(D(2024, 1, 1), 5), (D(2024, 1, 6), 2)]
    assert date_chunks(D(2024, 1, 1), D(2024, 1, 1), 5) == [(D(2024, 1, 1), 1)]


def test_date_chunks_empty_when_start_after_end() -> None:
    assert date_chunks(D(2024, 1, 2), D(2024, 1, 1), 5) == []


def availability(min_date: str, max_date: str) -> str:
    return f"data_id,min_date,max_date\nVIIRS_NOAA21_SP,{min_date},{max_date}\n"


def api_handler(available: str, requested: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/data_availability/" in path:
            return httpx.Response(200, text=available)
        requested.append(path)
        return httpx.Response(200, text=API_HEADER + "\n")

    return handler


def short_range(config: Config) -> Config:
    return dataclasses.replace(config, start=D(2024, 1, 1), end=D(2024, 1, 12))


def test_download_clamps_to_availability_and_reports_gaps(config: Config) -> None:
    config = short_range(config)
    requested: list[str] = []
    handler = api_handler(availability("2024-01-04", "2024-01-10"), requested)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = download_area(client, config, "Poland", "VIIRS_NOAA21_SP", KEY)

    assert [p.rsplit("/", 2)[1:] for p in requested] == [["5", "2024-01-04"], ["2", "2024-01-09"]]
    assert report.gaps == [
        "2024-01-01..2024-01-03 (before 2024-01-04)",
        "2024-01-11..2024-01-12 (after 2024-01-10)",
    ]


def test_download_resumes_from_cache_and_never_stores_key(config: Config) -> None:
    config = short_range(config)
    requested: list[str] = []
    handler = api_handler(availability("2023-01-01", "2026-01-01"), requested)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = download_area(client, config, "Poland", "VIIRS_NOAA21_SP", KEY)
        second = download_area(client, config, "Poland", "VIIRS_NOAA21_SP", KEY)

    assert (first.downloaded, second.downloaded, second.cached) == (3, 0, 3)
    chunk = api_chunk_path(config.paths.raw, "VIIRS_NOAA21_SP", "Poland", D(2024, 1, 1), 5)
    stored_url = json.loads(meta_path(chunk).read_text())["url"]
    assert KEY not in stored_url
    assert "<MAP_KEY>" in stored_url


def test_source_missing_from_availability_downloads_nothing(config: Config) -> None:
    requested: list[str] = []
    handler = api_handler("data_id,min_date,max_date\nMODIS_SP,2000-11-01,2026-06-30\n", requested)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = download_area(client, config, "Poland", "VIIRS_NOAA21_SP", KEY)

    assert requested == []
    assert report.gaps == ["2024-01-01..2024-12-31 (source not listed in data_availability)"]


def test_country_without_bbox_raises(config: Config) -> None:
    with httpx.Client() as client, pytest.raises(ValueError, match="country_bbox"):
        download_area(client, config, "Germany", "VIIRS_NOAA21_SP", KEY)


def test_invalid_map_key_is_rejected() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, text="Invalid MAP_KEY."))
    with httpx.Client(transport=transport) as client, pytest.raises(FirmsResponseError):
        check_map_key(client, "https://firms.test", "bad")


def test_valid_map_key_returns_status() -> None:
    status = {"transaction_limit": 5000, "current_transactions": 3}
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=status))
    with httpx.Client(transport=transport) as client:
        assert check_map_key(client, "https://firms.test", KEY) == status
