"""Load and check the known-incidents ground-truth file."""

from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = (
    "incident_id",
    "name",
    "country",
    "start_local",
    "latitude",
    "longitude",
    "coord_uncertainty_m",
    "source_url",
)


def load_ground_truth(path: Path) -> pd.DataFrame:
    """Read known incidents and add `start_utc`.

    `start_local` must be ISO 8601 with a UTC offset (e.g. 2024-05-12T03:15:00+02:00) so
    local reporting times convert to UTC without guessing the time zone.

    Raises:
        ValueError: On missing columns, duplicate ids, offset-less times or bad coordinates.
    """
    df = pd.read_csv(path)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    duplicated = df.loc[df["incident_id"].duplicated(), "incident_id"].tolist()
    if duplicated:
        raise ValueError(f"{path}: duplicate incident_id {duplicated}")

    naive = df.loc[~df["start_local"].str.contains(r"(?:[+-]\d\d:\d\d|Z)$"), "incident_id"]
    if not naive.empty:
        raise ValueError(f"{path}: start_local lacks a UTC offset for {naive.tolist()}")
    df["start_utc"] = pd.to_datetime(df["start_local"], format="ISO8601", utc=True)

    bad_coords = df.loc[
        ~df["latitude"].between(-90, 90) | ~df["longitude"].between(-180, 180), "incident_id"
    ]
    if not bad_coords.empty:
        raise ValueError(f"{path}: coordinates out of range for {bad_coords.tolist()}")
    return df
