import numpy as np

from tsproj.core.ts_core.pipeline import (
    _safe_corr,
    _diff_corr,
    _pairwise_finite_overlap,
    _corr_with_pvalue,
)


# -----------------------
# _safe_corr
# -----------------------

def test_safe_corr_perfect_positive():
    x = np.array([1, 2, 3, 4, 5], dtype=float)
    y = np.array([2, 4, 6, 8, 10], dtype=float)

    c = _safe_corr(x, y)
    assert np.isclose(c, 1.0)


def test_safe_corr_constant_returns_none():
    x = np.array([1, 1, 1, 1], dtype=float)
    y = np.array([2, 3, 4, 5], dtype=float)

    c = _safe_corr(x, y)
    assert c is None


def test_safe_corr_handles_nans():
    x = np.array([1, 2, np.nan, 4, 5], dtype=float)
    y = np.array([2, 4, 6, np.nan, 10], dtype=float)

    c = _safe_corr(x, y)
    assert isinstance(c, float) or c is None


# -----------------------
# _diff_corr
# -----------------------

def test_diff_corr_basic():
    x = np.array([1, 2, 4, 7, 11], dtype=float)
    y = np.array([3, 5, 9, 15, 23], dtype=float)

    c = _diff_corr(x, y)
    assert np.isclose(c, 1.0)


def test_diff_corr_too_short():
    x = np.array([1, 2], dtype=float)
    y = np.array([2, 3], dtype=float)

    c = _diff_corr(x, y)
    assert c is None


def test_diff_corr_constant_diff():
    x = np.array([1, 2, 3, 4], dtype=float)
    y = np.array([5, 5, 5, 5], dtype=float)

    c = _diff_corr(x, y)
    assert c is None


# -----------------------
# _pairwise_finite_overlap
# -----------------------

def test_pairwise_overlap_basic():
    years = [2000, 2001, 2002, 2003]
    x = np.array([1, 2, 3, 4], dtype=float)
    y = np.array([2, 3, 4, 5], dtype=float)

    xo, yo, yrs = _pairwise_finite_overlap(years, x, y)

    assert len(xo) == 4
    assert len(yo) == 4
    assert yrs == years


def test_pairwise_overlap_removes_nans():
    years = [2000, 2001, 2002, 2003]
    x = np.array([1, np.nan, 3, 4], dtype=float)
    y = np.array([2, 3, np.nan, 5], dtype=float)

    xo, yo, yrs = _pairwise_finite_overlap(years, x, y)

    # only index 0 and 3 survive
    assert len(xo) == 2
    assert yrs == [2000, 2003]


def test_pairwise_overlap_empty():
    years = [2000, 2001]
    x = np.array([np.nan, np.nan])
    y = np.array([np.nan, np.nan])

    xo, yo, yrs = _pairwise_finite_overlap(years, x, y)

    assert len(xo) == 0
    assert yrs == []
    
    
def test_corr_with_pvalue_perfect_positive():
    x = np.array([1, 2, 3, 4, 5], dtype=float)
    y = np.array([2, 4, 6, 8, 10], dtype=float)

    corr, pval = _corr_with_pvalue(x, y)

    assert np.isclose(corr, 1.0)
    assert pval is not None


def test_corr_with_pvalue_constant_returns_none():
    x = np.array([1, 1, 1, 1, 1], dtype=float)
    y = np.array([2, 3, 4, 5, 6], dtype=float)

    corr, pval = _corr_with_pvalue(x, y)

    assert corr is None
    assert pval is None


def test_corr_with_pvalue_too_short():
    x = np.array([1, 2], dtype=float)
    y = np.array([2, 3], dtype=float)

    corr, pval = _corr_with_pvalue(x, y)

    assert corr is None
    assert pval is None