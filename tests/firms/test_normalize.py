import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest

from firms_monitor.config import Config
from firms_monitor.firms.archive import archive_path
from firms_monitor.firms.area_api import api_chunk_path
from firms_monitor.firms.normalize import build_detections, detections_path, read_firms_csv
from tests.conftest import API_HEADER, MODIS_HEADER, VIIRS_HEADER


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_archive_viirs_row(tmp_path: Path) -> None:
    path = write(
        tmp_path / "a.csv",
        f"{VIIRS_HEADER}\n52.3,21.0,330,0.4,0.4,2024-05-12,0137,N,VIIRS,n,2,290,13.77,N,0\n",
    )
    row = read_firms_csv(path, "viirs-snpp").iloc[0]
    assert row["satellite"] == "S-NPP"
    assert row["acq_datetime_utc"] == pd.Timestamp("2024-05-12 01:37", tz="UTC")
    assert row["type"] == 0


def test_api_row_pads_time_and_has_null_type(tmp_path: Path) -> None:
    path = write(
        tmp_path / "b.csv",
        f"{API_HEADER}\n52.3,21.0,330,0.4,0.4,2024-05-12,7,N21,VIIRS,n,2,290,1.5,N\n",
    )
    row = read_firms_csv(path, "VIIRS_NOAA21_SP").iloc[0]
    assert row["acq_time"] == "0007"
    assert row["acq_datetime_utc"] == pd.Timestamp("2024-05-12 00:07", tz="UTC")
    assert row["satellite"] == "NOAA-21"
    assert pd.isna(row["type"])


@pytest.mark.parametrize(("code", "expected"), [("T", "Terra"), ("Aqua", "Aqua")])
def test_modis_satellite_codes(tmp_path: Path, code: str, expected: str) -> None:
    path = write(
        tmp_path / "m.csv",
        f"{MODIS_HEADER}\n51.5,18.3,320,1,1,2021-08-27,2020,{code},MODIS,100,6.1,290,118.3,N,0\n",
    )
    assert read_firms_csv(path, "modis").iloc[0]["satellite"] == expected


def test_unknown_modis_satellite_raises(tmp_path: Path) -> None:
    path = write(
        tmp_path / "m.csv",
        f"{MODIS_HEADER}\n51.5,18.3,320,1,1,2021-08-27,2020,X,MODIS,100,6.1,290,118.3,N,0\n",
    )
    with pytest.raises(ValueError, match="unrecognised MODIS"):
        read_firms_csv(path, "modis")


def test_build_filters_dates_dedupes_and_audits(config: Config) -> None:
    viirs_row = "52.3,21.0,330,0.4,0.4,{date},0137,N,VIIRS,n,2,290,13.77,N,0"
    rows = [viirs_row.format(date=d) for d in ("2023-12-31", "2024-05-12", "2024-05-12")]
    write(
        archive_path(config.paths.raw, "viirs-snpp", 2024, "Poland"),
        VIIRS_HEADER + "\n" + "\n".join(rows) + "\n",
    )
    write(
        api_chunk_path(config.paths.raw, "VIIRS_NOAA21_SP", "Poland", dt.date(2024, 5, 10), 5),
        f"{API_HEADER}\n52.3,21.0,330,0.4,0.4,2024-05-12,151,N21,VIIRS,n,2,290,9.0,N\n",
    )

    detections = build_detections(config, "Poland")

    assert len(detections) == 2
    assert sorted(detections["satellite"]) == ["NOAA-21", "S-NPP"]
    assert detections_path(config, "Poland").exists()
    audit = [
        json.loads(line) for line in (config.paths.out / "audit.jsonl").read_text().splitlines()
    ]
    assert [(r["step"], r["n_in"], r["n_out"]) for r in audit] == [
        ("firms.read", None, 4),
        ("firms.date_filter", 4, 3),
        ("firms.dedupe", 3, 2),
    ]


def test_build_without_downloads_raises(config: Config) -> None:
    with pytest.raises(FileNotFoundError, match="run `firms-monitor firms` first"):
        build_detections(config, "Poland")
