import httpx
import pytest

from firms_monitor.config import Config
from firms_monitor.firms.archive import archive_path, download_country_archive
from tests.conftest import VIIRS_HEADER


def test_downloads_each_product_year_then_reuses_cache(config: Config) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, text=VIIRS_HEADER + "\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = download_country_archive(client, config, "Poland")
        second = download_country_archive(client, config, "Poland")

    assert requested == [
        "/data/country/modis/2024/modis_2024_Poland.csv",
        "/data/country/viirs-snpp/2024/viirs-snpp_2024_Poland.csv",
    ]
    assert len(first.downloaded) == 2
    assert second.downloaded == []
    assert len(second.cached) == 2
    assert archive_path(config.paths.raw, "modis", 2024, "Poland").exists()


def test_missing_product_year_is_recorded_not_raised(config: Config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "modis" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, text=VIIRS_HEADER + "\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = download_country_archive(client, config, "Poland")

    assert report.missing == ["modis_2024_Poland.csv"]
    assert report.downloaded == ["viirs-snpp_2024_Poland.csv"]


def test_unknown_country_raises(config: Config) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(404))) as client,
        pytest.raises(ValueError, match="United_Kingdom"),
    ):
        download_country_archive(client, config, "United Kingdom")
