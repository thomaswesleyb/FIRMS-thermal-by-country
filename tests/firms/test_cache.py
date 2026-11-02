import json
from pathlib import Path

import httpx
import pytest

from firms_monitor.firms import cache
from firms_monitor.firms.cache import FirmsResponseError, fetch_csv, is_cached, meta_path
from tests.conftest import VIIRS_HEADER

SP_ROW = "52.3,21.0,330,0.4,0.4,2024-05-12,0137,N20,VIIRS,n,2,290,13.77,N,0"
NRT_ROW = "52.3,21.0,330,0.4,0.4,2024-05-12,0137,N20,VIIRS,n,2.0NRT,290,13.77,N,0"


def client_returning(*responses: httpx.Response) -> httpx.Client:
    queue = list(responses)
    return httpx.Client(transport=httpx.MockTransport(lambda _request: queue.pop(0)))


def test_fetch_writes_csv_and_metadata(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    body = f"{VIIRS_HEADER}\n{SP_ROW}\n"
    client = client_returning(httpx.Response(200, text=body))

    assert fetch_csv(client, "https://x/secret", dest, public_url="https://x/<MAP_KEY>")

    assert dest.read_text() == body
    meta = json.loads(meta_path(dest).read_text())
    assert meta["url"] == "https://x/<MAP_KEY>"
    assert meta["n_rows"] == 1
    assert meta["provisional"] is False
    assert is_cached(dest)
    assert not dest.with_name("out.csv.part").exists()


def test_fetch_returns_false_on_404_and_writes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    client = client_returning(httpx.Response(404, text="not found"))

    assert fetch_csv(client, "https://x", dest, public_url="https://x") is False
    assert not dest.exists()


def test_fetch_rejects_non_csv_body(tmp_path: Path) -> None:
    client = client_returning(httpx.Response(200, text="Invalid MAP_KEY."))

    with pytest.raises(FirmsResponseError, match="Invalid MAP_KEY"):
        fetch_csv(client, "https://x", tmp_path / "out.csv", public_url="https://x")
    assert not (tmp_path / "out.csv").exists()


def test_nrt_rows_mark_file_provisional_so_it_is_refetched(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    client = client_returning(httpx.Response(200, text=f"{VIIRS_HEADER}\n{NRT_ROW}\n"))

    fetch_csv(client, "https://x", dest, public_url="https://x")

    assert dest.exists()
    assert not is_cached(dest)


def test_file_without_metadata_is_not_cached(tmp_path: Path) -> None:
    dest = tmp_path / "out.csv"
    dest.write_text(VIIRS_HEADER)
    assert not is_cached(dest)


def test_retries_transient_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache.time, "sleep", lambda _seconds: None)
    client = client_returning(
        httpx.Response(503), httpx.Response(200, text=f"{VIIRS_HEADER}\n{SP_ROW}\n")
    )

    assert fetch_csv(client, "https://x", tmp_path / "out.csv", public_url="https://x")


def test_gives_up_after_max_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache.time, "sleep", lambda _seconds: None)
    client = client_returning(*[httpx.Response(503)] * cache.MAX_ATTEMPTS)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_csv(client, "https://x", tmp_path / "out.csv", public_url="https://x")
