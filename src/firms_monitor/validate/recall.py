"""Stage 6 recall test: does FIRMS see documented fires, and at which FRP threshold?

For each known incident, detections are matched within a sensor-specific radius (plus
the incident's own coordinate uncertainty) and a time window around the reported start.
Static land sources (FIRMS type 2) are counted but excluded, as the main pipeline will
exclude them.
"""

import dataclasses
from pathlib import Path

import geopandas as gpd
import pandas as pd

from firms_monitor.config import Config, ValidationConfig
from firms_monitor.firms.normalize import detections_path
from firms_monitor.match.significance import SignificanceRule, is_significant
from firms_monitor.validate.ground_truth import load_ground_truth

METRIC_CRS = "EPSG:3035"  # ETRS89 / LAEA Europe: metre units, low distortion across Europe
STATIC_LAND_SOURCE = 2
PRECISE_COORDS_MAX_M = 300


def match_incident(
    incident: pd.Series, detections: gpd.GeoDataFrame, validation: ValidationConfig
) -> gpd.GeoDataFrame:
    """Detections (in METRIC_CRS) within the incident's time window and radius.

    Returns the matching rows with an added `distance_m` column.
    """
    start = incident["start_utc"]
    window_start = start - pd.Timedelta(hours=validation.hours_before)
    window_end = start + pd.Timedelta(hours=validation.hours_after)
    in_window = detections[detections["acq_datetime_utc"].between(window_start, window_end)]

    point = gpd.GeoSeries.from_xy(
        [incident["longitude"]], [incident["latitude"]], crs="EPSG:4326"
    ).to_crs(METRIC_CRS)[0]
    distance = in_window.distance(point)
    radius = in_window["instrument"].map(validation.radius_m) + incident["coord_uncertainty_m"]
    matched = in_window[distance <= radius].copy()
    matched["distance_m"] = distance[distance <= radius].round(0)
    return matched


def summarise_incident(
    matched: gpd.GeoDataFrame, rule: SignificanceRule, thresholds: tuple[float, ...]
) -> dict[str, object]:
    """Detection statistics for one incident and whether it passes each FRP threshold."""
    is_static = matched["type"].eq(STATIC_LAND_SOURCE).fillna(False).astype(bool)
    usable = matched[~is_static]
    n_viirs = int(usable["instrument"].eq("VIIRS").sum())
    n_modis = int(usable["instrument"].eq("MODIS").sum())
    sum_frp = float(usable["frp"].sum())
    summary: dict[str, object] = {
        "n_viirs": n_viirs,
        "n_modis": n_modis,
        "n_static_excluded": int(is_static.sum()),
        "n_overpasses": usable[["satellite", "acq_datetime_utc"]].drop_duplicates().shape[0],
        "sum_frp_mw": round(sum_frp, 2),
        "max_frp_mw": round(float(usable["frp"].max()), 2) if len(usable) else 0.0,
        "first_detect_utc": usable["acq_datetime_utc"].min() if len(usable) else pd.NaT,
        "last_detect_utc": usable["acq_datetime_utc"].max() if len(usable) else pd.NaT,
        "min_distance_m": float(usable["distance_m"].min()) if len(usable) else None,
        "satellites": ",".join(sorted(usable["satellite"].unique())),
    }
    for threshold in thresholds:
        threshold_rule = dataclasses.replace(rule, min_sum_frp_mw=threshold)
        summary[f"detected_frp_ge_{threshold:g}"] = is_significant(
            n_viirs, n_modis, sum_frp, threshold_rule
        )
    return summary


def recall_summary(per_incident: pd.DataFrame, thresholds: tuple[float, ...]) -> pd.DataFrame:
    """Recall per FRP threshold, for all incidents and for precisely-located ones."""
    subsets = {
        "all": per_incident,
        "precise_coords": per_incident[per_incident["coord_uncertainty_m"] <= PRECISE_COORDS_MAX_M],
    }
    rows = []
    for threshold in thresholds:
        column = f"detected_frp_ge_{threshold:g}"
        for subset, incidents in subsets.items():
            hits = incidents[column]
            rows.append(
                {
                    "min_sum_frp_mw": threshold,
                    "subset": subset,
                    "n_incidents": len(hits),
                    "n_detected": int(hits.sum()),
                    "recall": round(hits.mean(), 3) if len(hits) else None,
                }
            )
    return pd.DataFrame(rows)


def load_detections(config: Config, countries: list[str]) -> gpd.GeoDataFrame:
    """Load normalised detections for `countries`, projected to METRIC_CRS.

    Raises:
        FileNotFoundError: If a country's detections have not been built yet.
    """
    frames = []
    for country in countries:
        path = detections_path(config, country)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found; add {country!r} to countries or validation_countries "
                "in config.yaml and run `firms-monitor firms`."
            )
        frames.append(gpd.read_parquet(path))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326").to_crs(
        METRIC_CRS
    )


def run_recall(config: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the recall test and write per-incident and summary CSVs under out/validation."""
    incidents = load_ground_truth(config.paths.ground_truth)
    detections = load_detections(config, sorted(incidents["country"].unique()))
    thresholds = config.validation.frp_thresholds_mw

    rows = []
    for _, incident in incidents.iterrows():
        matched = match_incident(incident, detections, config.validation)
        summary = summarise_incident(matched, config.significance, thresholds)
        rows.append({**incident.drop(["latitude", "longitude"]).to_dict(), **summary})
    per_incident = pd.DataFrame(rows)
    summary = recall_summary(per_incident, thresholds)

    out_dir: Path = config.paths.out / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    per_incident.to_csv(out_dir / "recall_by_incident.csv", index=False)
    summary.to_csv(out_dir / "recall_summary.csv", index=False)
    return per_incident, summary
