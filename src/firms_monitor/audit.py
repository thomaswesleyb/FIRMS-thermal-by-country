"""Append-only audit log: one JSON line per pipeline step, with counts in and out."""

import datetime as dt
import json
from pathlib import Path


def log_step(audit_path: Path, step: str, n_in: int | None, n_out: int, **details: object) -> None:
    """Append one audit record. `n_in` is None for steps that only produce rows."""
    record = {
        "time_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "step": step,
        "n_in": n_in,
        "n_out": n_out,
        **details,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a") as handle:
        handle.write(json.dumps(record, default=str) + "\n")
