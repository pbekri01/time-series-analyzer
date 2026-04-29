import numpy as np
import pandas as pd

from tsproj.core.ts_core.preprocess import zscore


def test_zscore_returns_nan_for_constant_series():
    s = pd.Series([5.0, 5.0, 5.0, 5.0])
    out = zscore(s)
    assert out.isna().all()


def test_zscore_ignores_nans_and_normalizes():
    s = pd.Series([1.0, 2.0, np.nan, 3.0, 4.0])
    out = zscore(s)

    finite = out.dropna().to_numpy()
    assert np.isclose(finite.mean(), 0.0, atol=1e-9)
    assert np.isclose(finite.std(ddof=0), 1.0, atol=1e-9)


def test_zscore_all_nan_stays_nan():
    s = pd.Series([np.nan, np.nan])
    out = zscore(s)
    assert out.isna().all()