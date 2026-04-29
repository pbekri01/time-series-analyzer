from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

try:
    from statsmodels.tsa.seasonal import STL
except Exception:  # pragma: no cover
    STL = None

@dataclass
class DecompResult:
    trend: np.ndarray
    seasonal: np.ndarray
    resid: np.ndarray

def decompose_series(y: np.ndarray, period: int = 1) -> DecompResult:
    """
    Uses STL if available and period>=2; otherwise returns trend via moving average
    and sets seasonal=0.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 3:
        return DecompResult(trend=np.copy(y), seasonal=np.zeros(n), resid=np.zeros(n))

    if period >= 2 and STL is not None and n >= 2 * period:
        stl = STL(y, period=period, robust=True)
        res = stl.fit()
        trend = res.trend
        seasonal = res.seasonal
        resid = res.resid
        return DecompResult(trend=trend, seasonal=seasonal, resid=resid)

    # Fallback: simple moving average trend (window ~ min(11, n//3))
    w = max(3, min(11, n // 3 if n // 3 >= 3 else 3))
    trend = pd.Series(y).rolling(window=w, center=True, min_periods=1).mean().to_numpy()
    seasonal = np.zeros(n)
    resid = y - trend
    return DecompResult(trend=trend, seasonal=seasonal, resid=resid)
    

