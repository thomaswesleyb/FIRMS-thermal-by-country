"""Load config.yaml into typed, immutable settings."""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import yaml

from firms_monitor.match.significance import SignificanceRule

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class FirmsConfig:
    """FIRMS download settings."""

    archive_base_url: str
    archive_products: tuple[str, ...]
    api_base_url: str
    api_sources: tuple[str, ...]
    api_max_day_range: int
    api_min_request_interval_s: float
    country_bbox: dict[str, BBox]


@dataclass(frozen=True)
class ValidationConfig:
    """Recall-test matching settings."""

    radius_m: dict[str, float]
    hours_before: float
    hours_after: float
    frp_thresholds_mw: tuple[float, ...]


@dataclass(frozen=True)
class Paths:
    """Data directories and the ground-truth file."""

    raw: Path
    interim: Path
    out: Path
    ground_truth: Path


@dataclass(frozen=True)
class Config:
    """Top-level pipeline settings from config.yaml."""

    countries: tuple[str, ...]
    validation_countries: tuple[str, ...]
    start: dt.date
    end: dt.date
    paths: Paths
    firms: FirmsConfig
    significance: SignificanceRule
    validation: ValidationConfig

    @property
    def all_countries(self) -> tuple[str, ...]:
        """Pilot countries followed by validation-only countries, without duplicates."""
        return tuple(dict.fromkeys(self.countries + self.validation_countries))


def load_config(path: Path) -> Config:
    """Parse config.yaml. Paths are resolved relative to the config file's directory.

    Raises:
        ValueError: If a required key is missing or the date range is inverted.
    """
    raw = yaml.safe_load(path.read_text())
    root = path.resolve().parent
    try:
        config = _build(raw, root)
    except KeyError as exc:
        raise ValueError(f"{path}: missing required key {exc}") from exc
    if config.start > config.end:
        raise ValueError(f"{path}: date_range.start {config.start} is after end {config.end}")
    return config


def _build(raw: dict, root: Path) -> Config:
    firms = raw["firms"]
    validation = raw["validation"]
    return Config(
        countries=tuple(raw["countries"]),
        validation_countries=tuple(raw.get("validation_countries", [])),
        start=raw["date_range"]["start"],
        end=raw["date_range"]["end"],
        paths=Paths(**{key: root / value for key, value in raw["paths"].items()}),
        firms=FirmsConfig(
            archive_base_url=firms["archive_base_url"],
            archive_products=tuple(firms["archive_products"]),
            api_base_url=firms["api_base_url"],
            api_sources=tuple(firms["api_sources"]),
            api_max_day_range=firms["api_max_day_range"],
            api_min_request_interval_s=firms["api_min_request_interval_s"],
            country_bbox={name: tuple(box) for name, box in firms["country_bbox"].items()},
        ),
        significance=SignificanceRule(**raw["significance"]),
        validation=ValidationConfig(
            radius_m=validation["radius_m"],
            hours_before=validation["hours_before"],
            hours_after=validation["hours_after"],
            frp_thresholds_mw=tuple(validation["frp_thresholds_mw"]),
        ),
    )
