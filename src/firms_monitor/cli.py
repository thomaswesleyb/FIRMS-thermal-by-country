"""Command-line entry point: one subcommand per implemented stage, plus run-all."""

import argparse
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from firms_monitor.audit import log_step
from firms_monitor.config import Config, load_config
from firms_monitor.firms.archive import download_country_archive
from firms_monitor.firms.area_api import check_map_key, download_area
from firms_monitor.firms.normalize import build_detections
from firms_monitor.validate.recall import run_recall

log = logging.getLogger("firms_monitor")
HTTP_TIMEOUT_S = 120.0


def stage_firms(config: Config, countries: tuple[str, ...]) -> None:
    """Stage 3: download (or reuse cached) FIRMS data and build detections GeoParquet."""
    audit = config.paths.out / "audit.jsonl"
    map_key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    with httpx.Client(timeout=HTTP_TIMEOUT_S, follow_redirects=True) as client:
        if map_key:
            check_map_key(client, config.firms.api_base_url, map_key)
        else:
            log.warning(
                "FIRMS_MAP_KEY not set: skipping Area API sources %s. Detections from "
                "those satellites will be missing.",
                list(config.firms.api_sources),
            )
        for country in countries:
            archive = download_country_archive(client, config, country)
            log.info(
                "%s archive: %d downloaded, %d cached, missing %s",
                country,
                len(archive.downloaded),
                len(archive.cached),
                archive.missing,
            )
            log_step(
                audit,
                "firms.download_archive",
                None,
                len(archive.downloaded) + len(archive.cached),
                country=country,
                missing=archive.missing,
            )
            _download_api_sources(client, config, country, map_key)
            detections = build_detections(config, country)
            log.info("%s: %d detections written", country, len(detections))


def _download_api_sources(client: httpx.Client, config: Config, country: str, map_key: str) -> None:
    audit = config.paths.out / "audit.jsonl"
    for source in config.firms.api_sources:
        if not map_key:
            log_step(
                audit,
                "firms.download_api",
                None,
                0,
                country=country,
                source=source,
                gaps=["all dates (FIRMS_MAP_KEY not set)"],
            )
            continue
        report = download_area(client, config, country, source, map_key)
        log.info(
            "%s %s: %d downloaded, %d cached, gaps %s",
            country,
            source,
            report.downloaded,
            report.cached,
            report.gaps,
        )
        log_step(
            audit,
            "firms.download_api",
            None,
            report.downloaded + report.cached,
            country=country,
            source=source,
            gaps=report.gaps,
        )


def stage_validate(config: Config) -> None:
    """Stage 6: recall of known incidents per FRP threshold."""
    per_incident, summary = run_recall(config)
    columns = [
        "incident_id",
        "n_viirs",
        "n_modis",
        "n_static_excluded",
        "sum_frp_mw",
        "max_frp_mw",
        "min_distance_m",
        "satellites",
    ]
    print(per_incident[columns].to_string(index=False))
    print()
    print(summary.to_string(index=False))


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and run the requested stage."""
    parser = argparse.ArgumentParser(prog="firms-monitor")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    firms = commands.add_parser("firms", help="Stage 3: download FIRMS data, build detections")
    firms.add_argument(
        "--country",
        action="append",
        help="Limit to this country (repeatable). Default: countries + validation_countries.",
    )
    commands.add_parser("validate", help="Stage 6: recall test against known incidents")
    commands.add_parser("run-all", help="Run every implemented stage in order")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs full request URLs at INFO, and Area API URLs embed the MAP_KEY.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()
    config = load_config(args.config)

    if args.command == "firms":
        stage_firms(config, tuple(args.country) if args.country else config.all_countries)
    elif args.command == "validate":
        stage_validate(config)
    elif args.command == "run-all":
        stage_firms(config, config.all_countries)
        stage_validate(config)
