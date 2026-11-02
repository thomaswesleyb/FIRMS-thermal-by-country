import datetime as dt
from pathlib import Path

import pytest
import yaml

from firms_monitor.config import Config, load_config

VIIRS_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_ti5,frp,daynight,type"
)
MODIS_HEADER = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_t31,frp,daynight,type"
)
API_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_ti5,frp,daynight"
)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    raw = {
        "countries": ["Poland"],
        "validation_countries": [],
        "date_range": {"start": dt.date(2024, 1, 1), "end": dt.date(2024, 12, 31)},
        "paths": {
            "raw": "data/raw",
            "interim": "data/interim",
            "out": "data/out",
            "ground_truth": "known_incidents.csv",
        },
        "firms": {
            "archive_base_url": "https://firms.test/data/country",
            "archive_products": ["modis", "viirs-snpp"],
            "api_base_url": "https://firms.test",
            "api_sources": ["VIIRS_NOAA21_SP"],
            "api_max_day_range": 5,
            "api_min_request_interval_s": 0,
            "country_bbox": {"Poland": [14.07, 49.0, 24.15, 54.84]},
        },
        "significance": {
            "min_viirs_detections": 2,
            "min_modis_detections": 1,
            "min_sum_frp_mw": 20.0,
        },
        "validation": {
            "radius_m": {"VIIRS": 400, "MODIS": 1000},
            "hours_before": 6,
            "hours_after": 72,
            "frp_thresholds_mw": [0, 20],
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))
    return load_config(path)
