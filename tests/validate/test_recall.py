import geopandas as gpd
import pandas as pd

from firms_monitor.config import Config
from firms_monitor.validate.recall import (
    METRIC_CRS,
    match_incident,
    recall_summary,
    summarise_incident,
)

START = pd.Timestamp("2024-05-12 01:15", tz="UTC")
LAT, LON = 52.0, 20.0
METRES_PER_DEG_LAT = 111_200


def incident(uncertainty_m: float = 0) -> pd.Series:
    return pd.Series(
        {
            "latitude": LAT,
            "longitude": LON,
            "start_utc": START,
            "coord_uncertainty_m": uncertainty_m,
        }
    )


def detections(rows: list[dict]) -> gpd.GeoDataFrame:
    """Rows give north_m (offset north of the incident), hours, instrument, frp, type."""
    df = pd.DataFrame(rows)
    df["acq_datetime_utc"] = START + pd.to_timedelta(df["hours"], unit="h")
    df["satellite"] = df["instrument"].map({"VIIRS": "NOAA-20", "MODIS": "Terra"})
    lat = LAT + df["north_m"] / METRES_PER_DEG_LAT
    points = gpd.points_from_xy([LON] * len(df), lat, crs="EPSG:4326")
    return gpd.GeoDataFrame(df, geometry=points).to_crs(METRIC_CRS)


def row(north_m: float, hours: float, instrument: str = "VIIRS", frp: float = 10.0, type_=0):
    return {"north_m": north_m, "hours": hours, "instrument": instrument, "frp": frp, "type": type_}


def test_radius_depends_on_instrument_and_coordinate_uncertainty(config: Config) -> None:
    dets = detections([row(350, 1), row(700, 1), row(700, 1, "MODIS"), row(1500, 1, "MODIS")])

    matched = match_incident(incident(), dets, config.validation)
    assert sorted(matched["north_m"].tolist()) == [350, 700]
    assert set(matched["instrument"]) == {"VIIRS", "MODIS"}

    widened = match_incident(incident(uncertainty_m=600), dets, config.validation)
    assert len(widened) == 4


def test_time_window_edges(config: Config) -> None:
    dets = detections([row(0, -6), row(0, -6.1), row(0, 72), row(0, 72.1)])
    matched = match_incident(incident(), dets, config.validation)
    assert sorted(matched["hours"].tolist()) == [-6, 72]


def test_summary_excludes_static_sources_and_applies_thresholds(config: Config) -> None:
    dets = detections([row(0, 1, frp=12), row(0, 2, frp=12), row(0, 3, frp=500, type_=2)])
    matched = match_incident(incident(), dets, config.validation)

    summary = summarise_incident(matched, config.significance, (0, 20, 50))

    assert summary["n_viirs"] == 2
    assert summary["n_static_excluded"] == 1
    assert summary["sum_frp_mw"] == 24
    assert summary["n_overpasses"] == 2
    assert summary["detected_frp_ge_0"] is True
    assert summary["detected_frp_ge_20"] is True
    assert summary["detected_frp_ge_50"] is False


def test_summary_with_no_detections(config: Config) -> None:
    matched = match_incident(incident(), detections([row(5000, 1)]), config.validation)
    summary = summarise_incident(matched, config.significance, (0,))
    assert summary["n_viirs"] == 0
    assert summary["max_frp_mw"] == 0.0
    assert summary["detected_frp_ge_0"] is False


def test_recall_summary_splits_precise_coordinates() -> None:
    per_incident = pd.DataFrame(
        {"coord_uncertainty_m": [100, 100, 1500], "detected_frp_ge_20": [True, False, True]}
    )
    summary = recall_summary(per_incident, (20,)).set_index("subset")
    assert summary.loc["all", "recall"] == round(2 / 3, 3)
    assert summary.loc["precise_coords", "recall"] == 0.5
