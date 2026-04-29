import numpy as np

from tsproj.core.ts_core.xcorr import cross_correlation


def test_cross_correlation_detects_perfect_lag0_match():
    x = np.array([1, 2, 3, 4, 5], dtype=float)
    y = np.array([1, 2, 3, 4, 5], dtype=float)

    result = cross_correlation(x, y, max_lag=2, min_overlap=3)

    assert result["best"]["lag"] == 0
    assert np.isclose(result["best"]["correlation"], 1.0)


def test_cross_correlation_returns_none_when_overlap_too_small():
    x = np.array([1, 2], dtype=float)
    y = np.array([1, 2], dtype=float)

    result = cross_correlation(x, y, max_lag=2, min_overlap=3)

    assert result["best"]["correlation"] is None


def test_cross_correlation_handles_constant_series():
    x = np.array([1, 1, 1, 1, 1], dtype=float)
    y = np.array([2, 2, 2, 2, 2], dtype=float)

    result = cross_correlation(x, y, max_lag=1, min_overlap=3)

    assert result["best"]["correlation"] is None