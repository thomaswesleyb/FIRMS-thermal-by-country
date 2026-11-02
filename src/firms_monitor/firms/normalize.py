"""Merge cached FIRMS CSVs into one GeoParquet of detections per country."""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from firms_monitor.audit import log_step
from firms_monitor.config import Config
from firms_monitor.firms.archive import archive_path

OUTPUT_COLUMNS = [
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "acq_datetime_utc",
    "satellite",
    "instrument",
    "product",
    "confidence",
    "frp",
    "daynight",
    "type",
    "version",
    "source_file",
]
DEDUP_KEY = ["latitude", "longitude", "acq_datetime_utc", "satellite"]

PRODUCT_SATELLITE = {
    "viirs-snpp": "S-NPP",
    "viirs-jpss1": "NOAA-20",
    "viirs-jpss2": "NOAA-21",
    "VIIRS_SNPP_SP": "S-NPP",
    "VIIRS_NOAA20_SP": "NOAA-20",
    "VIIRS_NOAA21_SP": "NOAA-21",
}
MODIS_SATELLITE = {"Terra": "Terra", "T": "Terra", "Aqua": "Aqua", "A": "Aqua"}


def read_firms_csv(path: Path, product: str) -> pd.DataFrame:
    """Read one FIRMS CSV (archive or Area API) into the common detection schema.

    `satellite` is normalised to Terra, Aqua, S-NPP, NOAA-20 or NOAA-21. `type` is
    null where the source omits it (Area API).

    Raises:
        ValueError: If a MODIS row has an unrecognised satellite code.
    """
    df = pd.read_csv(
        path, dtype={"acq_time": str, "confidence": str, "version": str, "satellite": str}
    )
    df["acq_time"] = df["acq_time"].str.zfill(4)
    df["acq_datetime_utc"] = pd.to_datetime(
        df["acq_date"] + " " + df["acq_time"], format="%Y-%m-%d %H%M", utc=True
    )
    df["satellite"] = _normalise_satellite(df["satellite"], product, path)
    df["product"] = product
    if "type" not in df.columns:
        df["type"] = pd.NA
    df["type"] = df["type"].astype("Int8")
    df["source_file"] = path.name
    return df[OUTPUT_COLUMNS]


def _normalise_satellite(raw: pd.Series, product: str, path: Path) -> pd.Series:
    if product in PRODUCT_SATELLITE:
        return pd.Series(PRODUCT_SATELLITE[product], index=raw.index, dtype="str")
    mapped = raw.map(MODIS_SATELLITE)
    unknown = sorted(set(raw[mapped.isna()]))
    if unknown:
        raise ValueError(f"{path}: unrecognised MODIS satellite codes {unknown}")
    return mapped.astype("str")


def cached_files(config: Config, country: str) -> list[tuple[Path, str]]:
    """All cached (csv_path, product) pairs for `country`, archive and Area API."""
    archive_files = [
        (archive_path(config.paths.raw, product, year, country), product)
        for product in config.firms.archive_products
        for year in range(config.start.year, config.end.year + 1)
    ]
    api_files = [
        (path, source)
        for source in config.firms.api_sources
        for path in sorted(
            (config.paths.raw / "firms" / "area_api" / source / country).glob("*.csv")
        )
    ]
    return [(path, product) for path, product in archive_files + api_files if path.exists()]


def detections_path(config: Config, country: str) -> Path:
    """Path of the normalised detections GeoParquet for `country`."""
    return config.paths.interim / "firms" / f"detections_{country}.parquet"


def build_detections(config: Config, country: str) -> gpd.GeoDataFrame:
    """Merge, date-filter and de-duplicate cached detections; write GeoParquet.

    Raises:
        FileNotFoundError: If nothing has been downloaded for `country` yet.
    """
    files = cached_files(config, country)
    if not files:
        raise FileNotFoundError(
            f"No cached FIRMS files for {country!r}; run `firms-monitor firms` first."
        )
    raw = pd.concat([read_firms_csv(path, product) for path, product in files], ignore_index=True)
    audit = config.paths.out / "audit.jsonl"
    log_step(audit, "firms.read", None, len(raw), country=country, n_files=len(files))

    dates = raw["acq_datetime_utc"].dt.date
    in_range = raw[(dates >= config.start) & (dates <= config.end)]
    log_step(
        audit,
        "firms.date_filter",
        len(raw),
        len(in_range),
        country=country,
        start=config.start,
        end=config.end,
    )

    deduped = in_range.drop_duplicates(subset=DEDUP_KEY).reset_index(drop=True)
    log_step(audit, "firms.dedupe", len(in_range), len(deduped), country=country, key=DEDUP_KEY)

    detections = gpd.GeoDataFrame(
        deduped,
        geometry=gpd.points_from_xy(deduped["longitude"], deduped["latitude"]),
        crs="EPSG:4326",
    )
    out = detections_path(config, country)
    out.parent.mkdir(parents=True, exist_ok=True)
    detections.to_parquet(out)
    return detections
