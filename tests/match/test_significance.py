import pytest

from firms_monitor.match.significance import SignificanceRule, is_significant

RULE = SignificanceRule(min_viirs_detections=2, min_modis_detections=1, min_sum_frp_mw=20.0)


@pytest.mark.parametrize(
    ("n_viirs", "n_modis", "sum_frp", "expected"),
    [
        (2, 0, 20.0, True),  # VIIRS count and FRP exactly at threshold
        (1, 0, 500.0, False),  # one VIIRS detection is never enough
        (0, 1, 20.0, True),  # any MODIS detection is enough
        (1, 1, 25.0, True),
        (5, 3, 19.99, False),  # enough detections, FRP just below threshold
        (0, 0, 0.0, False),
    ],
)
def test_is_significant(n_viirs: int, n_modis: int, sum_frp: float, expected: bool) -> None:
    assert is_significant(n_viirs, n_modis, sum_frp, RULE) is expected
