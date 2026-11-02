# FIRMS-thermal-by-country

Can NASA FIRMS satellite fire detections reveal large fires at warehouses in European
defense supply chains, independently of media reporting, and is there a change after
February 2022 relative to comparable non-defense sites?

Pilot: Poland, 2019-01-01 to 2025-12-31. See [docs/PLAN.md](docs/PLAN.md) for the staged
plan and the first feasibility results.

## Status

| Stage | What | State |
|---|---|---|
| 1 | Company registry | not started |
| 2 / 2b | Site geocoding, control set | not started |
| 3 | FIRMS download and normalisation | **done** |
| 4 | Matching, event clustering, filtering | significance rule only |
| 5 | Media linking (GDELT) | not started |
| 6 | Validation against known incidents | **recall test done**; precision review pending |

## Setup

```sh
uv sync
cp .env.example .env      # add FIRMS_MAP_KEY (free: https://firms.modaps.eosdis.nasa.gov/api/map_key/)
prek install
```

Without `FIRMS_MAP_KEY` the pipeline still runs. MODIS, VIIRS S-NPP and VIIRS NOAA-20 come
from the public country archive. VIIRS NOAA-21 (Area API only) is skipped, with a warning
and a gap recorded in the audit log.

## Commands

All settings live in `config.yaml`.

```sh
uv run firms-monitor firms                    # Stage 3: download + build detections (all configured countries)
uv run firms-monitor firms --country Poland   # one country
uv run firms-monitor validate                 # Stage 6: recall of known incidents per FRP threshold
uv run firms-monitor run-all
```

Downloads are cached under `data/raw/firms/` with a `.meta.json` sidecar for each file
(source URL, SHA-256, Last-Modified). Reruns skip cached files. Files that still contain
near-real-time rows are fetched again until FIRMS replaces them with standard-processing
data. Every filtering step appends counts in/out to `data/out/audit.jsonl`.

## Data sources

- **FIRMS country archive** (`/data/country/{product}/{year}/{product}_{year}_{Country}.csv`):
  yearly files of standard-processing data with the `type` field (2 = static land source).
  No key needed. NOAA-21 is not published there.
- **FIRMS Area API**: bounding box, at most 5 days per request, 5000 transactions per 10
  min per MAP_KEY. The downloader clamps to the range `/api/data_availability` reports.
- **Ground truth**: `data/ground_truth/known_incidents.csv`, with documented fires,
  local start times with UTC offset, coordinate uncertainty and a source URL per row.

## Data handling

`data/raw`, `data/interim`, `data/out` and all `*.parquet` files are git-ignored. The
site registry (Stage 1–2) is a compiled list of defense-supply-chain locations. Never
commit it or any site-level output. Anything published should be aggregated.

## Limitations

- **Overpass timing.** Polar orbiters see a given place a few times a day: VIIRS around
  01:30 and 13:30 local per satellite, MODIS Terra/Aqua around 10:30/22:30 and
  13:30/01:30. A fire that flares and is knocked down between overpasses is not seen.
- **Cloud cover** blocks detection entirely, and FIRMS does not flag cloud-missed fires.
- **Minimum detectable fire.** VIIRS 375 m can detect a few hundred m² of open flame,
  but fires inside intact buildings, or under a roof that hasn't failed, emit little to
  the sensor.
- **FRP.** VIIRS FRP comes from the 750 m M13 band and is split equally among the 375 m
  pixels inside it, so identical FRP values in one overpass are expected, not
  duplicates. Very intense fires can saturate M13 and report FRP = 0.
- **NOAA-21** detections come only through the Area API, have no `type` field, and need
  a MAP_KEY.
- **Geocoding error.** Site and incident coordinates carry uncertainty. Village-level
  ground-truth coordinates are ±1.5 km.
- **Company-list completeness** will be uneven by country (Stage 1), and so will media
  reporting (Stage 5).
