import numpy as np

from tsproj.core.ts_core.stationarity import StationarityAnalyzer


def test_stationarity_short_series_fails_cleanly():
    analyzer = StationarityAnalyzer(min_length=8)
    y = np.array([1.0, 2.0, 3.0])

    result = analyzer.analyze(y)

    assert result.success is False
    assert result.original_p_value is None
    assert "too short" in result.reason.lower()


def test_stationarity_constant_series_returns_safe_failure():
    analyzer = StationarityAnalyzer(min_length=5)
    y = np.array([3.0, 3.0, 3.0, 3.0, 3.0, 3.0])

    result = analyzer.analyze(y)

    assert result.success is False or result.final_p_value is None


def test_stationarity_removes_non_finite_values():
    analyzer = StationarityAnalyzer(min_length=5)
    y = np.array([1.0, 2.0, np.nan, 3.0, 4.0, 5.0, np.inf, 6.0])

    result = analyzer.analyze(y)

    assert len(result.series_transformed) <= 6