# Plan

## Directory layout

Directories marked *(planned)* are created when their stage is built, not before.

```
config.yaml                     all settings (countries, dates, thresholds, URLs)
.env                            FIRMS_MAP_KEY (git-ignored; see .env.example)
data/
  ground_truth/known_incidents.csv   committed: public, documented incidents
  raw/firms/country_archive/    yearly country CSVs + .meta.json   (git-ignored)
  raw/firms/area_api/           5-day bbox chunks + .meta.json     (git-ignored)
  interim/firms/detections_<Country>.parquet                       (git-ignored)
  out/audit.jsonl               counts in/out for each step        (git-ignored)
  out/validation/               recall_by_incident.csv, recall_summary.csv
src/firms_monitor/
  cli.py                        one subcommand per stage + run-all
  config.py                     typed config loader
  audit.py                      append-only audit log
  firms/                        Stage 3: archive.py, area_api.py, cache.py, normalize.py
  match/significance.py         Stage 4 significance rule (shared with Stage 6)
  validate/                     Stage 6: ground_truth.py, recall.py
  sites/                        (planned) Stage 1–2b: source stubs, registry, geocoding, controls
  match/ (rest)                 (planned) Stage 4: buffers, joins, clustering, hotspot filter
  media/                        (planned) Stage 5: GDELT DOC 2.0 linking
tests/                          mirrors src/
notebooks/                      (planned) exploration only
```

## Stage order

1. **Stage 3 + Stage 6 recall (done).** Detection feasibility was the biggest unknown.
2. **Stage 6 decision.** Choose the significance rule from the recall results below,
   then expand the ground truth (target 30+ incidents with building-level coordinates).
3. **Stage 4.** Site buffers, spatial join, 48 h event clustering, persistent-hotspot
   filter (> N distinct days/year), drop `type == 2`, land-cover and season flags.
   Requires a site layer, so it is developed against the ground-truth points first.
4. **Stage 1–2 pilot.** About 50 Polish companies entered by hand in CSV with provenance,
   OSM footprints via Overpass, and fuzzy name/operator matching within 500 m.
5. **Stage 2b controls.** 3–5 OSM warehouse/industrial footprints per site, matched
   on region, footprint area and WorldCover urban/rural class.
6. **Stage 5 media.** GDELT DOC 2.0, window −1/+7 days, local-language terms, links
   and titles only.
7. **Stage 6 precision.** Manual review of 50 flagged events. Then scale to other
   countries.

## Feasibility check, 2026-11-02

Data: MODIS, VIIRS S-NPP and NOAA-20 from the country archive (no NOAA-21; no MAP_KEY
yet). Matching: within 400 m (VIIRS) / 1000 m (MODIS) plus each incident's coordinate
uncertainty, from −6 h to +72 h around the reported start. Static sources (`type` 2)
excluded.

| Incident | VIIRS | MODIS | ΣFRP MW | Note |
|---|---|---|---|---|
| Marywilska 44, Warsaw (2024-05-12) | 2 | 0 | 27.5 | NOAA-20 01:37 UTC, 22 min after start |
| Diehl, Berlin (2024-05-03) | 1 | 0 | 15.2 | fails the "≥2 VIIRS" rule on count alone |
| Przylep hazardous waste (2023-07-22) | 4 | 0 | 6.2 | started after the afternoon pass; seen only that night |
| Muchy pallet hall (2021-08-27) | 3 | 4 | 172.4 | Terra night pass 1 h after start |
| IKEA Vilnius, Leyton, Gdańsk port, Bydgoszcz, Waszkowo, Zajączki, Kęty | 0 | 0 | 0 | nothing within 5 km over ±days |

Recall by summed-FRP threshold, with the count rule fixed at ≥2 VIIRS OR ≥1 MODIS:

| min ΣFRP | 0 | 5 | 10 | 20 | 50 | 100 |
|---|---|---|---|---|---|---|
| recall (n=11) | 3/11 | 3/11 | 2/11 | 2/11 | 1/11 | 1/11 |

What this means:

- **Recall is low (~20–35%), and timing drives it more than fire size.** The 6500 m²
  Gdańsk port fire burned for 4 days without a single detection, while a pallet hall in
  Muchy produced 172 MW because Terra passed an hour after ignition.
- **A 20 MW threshold drops real fires.** Przylep was a major fire but only its tail was
  observed (6 MW). Diehl had one 15 MW detection. Lowering the threshold to about 5 MW
  and adding a 1-VIIRS-with-high-FRP path would recover both. Precision then has to come
  from the hotspot filter and land cover, to be checked in the Stage 6 precision review.
- **NOAA-21 is the cheapest recall gain.** It adds about two passes per day around 50
  minutes from NOAA-20. It needs a MAP_KEY, and standard-processing coverage must be
  confirmed via `/api/data_availability`.
- **For the difference-in-differences design, low recall is acceptable if it does not
  differ between groups.** Defense and control sites are observed by the same sensors
  with the same timing. Matching controls on urban/rural setting and region keeps cloud
  and overpass geometry comparable. The cost is statistical power, not bias. The
  ground-truth set is too small to estimate recall separately by group.
- **Four Polish incidents have village-level coordinates (±1.5 km).** Refining them to
  building footprints would tighten the test.
