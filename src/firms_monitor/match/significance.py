"""Significance rule for fire events (Stage 4), shared with the Stage 6 recall test."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SignificanceRule:
    """An event is significant if it has enough detections AND enough summed FRP.

    "Enough detections" means at least `min_viirs_detections` VIIRS detections OR at
    least `min_modis_detections` MODIS detections.
    """

    min_viirs_detections: int
    min_modis_detections: int
    min_sum_frp_mw: float


def is_significant(n_viirs: int, n_modis: int, sum_frp_mw: float, rule: SignificanceRule) -> bool:
    """Apply `rule` to one event's detection counts and summed FRP (MW)."""
    enough_detections = n_viirs >= rule.min_viirs_detections or n_modis >= rule.min_modis_detections
    return enough_detections and sum_frp_mw >= rule.min_sum_frp_mw
