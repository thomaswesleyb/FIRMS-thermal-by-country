from pathlib import Path

import pandas as pd
import pytest

from firms_monitor.validate.ground_truth import load_ground_truth

HEADER = "incident_id,name,country,start_local,latitude,longitude,coord_uncertainty_m,source_url"
GOOD = "a,Hall A,Poland,2024-05-12T03:15:00+02:00,52.32,21.01,150,https://example.org/a"


def write(tmp_path: Path, *rows: str, header: str = HEADER) -> Path:
    path = tmp_path / "gt.csv"
    path.write_text("\n".join([header, *rows]) + "\n")
    return path


def test_converts_local_time_to_utc(tmp_path: Path) -> None:
    df = load_ground_truth(write(tmp_path, GOOD))
    assert df.loc[0, "start_utc"] == pd.Timestamp("2024-05-12 01:15", tz="UTC")


def test_rejects_time_without_offset(tmp_path: Path) -> None:
    row = GOOD.replace("+02:00", "")
    with pytest.raises(ValueError, match="lacks a UTC offset"):
        load_ground_truth(write(tmp_path, row))


def test_rejects_duplicate_ids(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        load_ground_truth(write(tmp_path, GOOD, GOOD))


def test_rejects_out_of_range_coordinates(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="out of range"):
        load_ground_truth(write(tmp_path, GOOD.replace("52.32", "152.32")))


def test_rejects_missing_columns(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_url"):
        load_ground_truth(write(tmp_path, GOOD.rsplit(",", 1)[0], header=HEADER.rsplit(",", 1)[0]))


def test_repository_ground_truth_file_is_valid() -> None:
    df = load_ground_truth(Path(__file__).parents[2] / "data/ground_truth/known_incidents.csv")
    assert len(df) >= 4
