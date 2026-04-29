from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Any


def _finite_or_none(x: Any) -> Optional[float]:
    try:
        fx = float(x)
    except Exception:
        return None
    return fx if np.isfinite(fx) else None


def cross_correlation(
    x: np.ndarray,
    y: np.ndarray,
    max_lag: int = 10,
    min_overlap: int = 3,
) -> Dict[str, object]:
    """
    Pearson-style cross-correlation across lags.

    Lag convention:
    - positive lag k: y may precede x by k time-steps
    - negative lag k: x may precede y by abs(k) time-steps
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)

    n = min(len(x), len(y))
    lags = list(range(-max_lag, max_lag + 1))

    if n == 0:
        return {
            "lags": lags,
            "correlations": [None for _ in lags],
            "overlap_n": [0 for _ in lags],
            "best": {
                "lag": None,
                "correlation": None,
                "max_abs_correlation": None,
                "overlap_n": None,
                "score": None,
                "overlap_n_lag0": 0,
            },
        }

    # Use common tail so behavior matches the rest of pipeline helpers
    x = x[-n:]
    y = y[-n:]

    corrs: List[Optional[float]] = []
    overlaps: List[int] = []

    for k in lags:
        if k < 0:
            xa = x[:k]
            ya = y[-k:]
        elif k > 0:
            xa = x[k:]
            ya = y[:-k]
        else:
            xa = x
            ya = y

        if xa.size == 0 or ya.size == 0:
            overlaps.append(0)
            corrs.append(None)
            continue

        mask = np.isfinite(xa) & np.isfinite(ya)
        xa2 = xa[mask]
        ya2 = ya[mask]
        ov = int(xa2.size)
        overlaps.append(ov)

        if ov < int(min_overlap):
            corrs.append(None)
            continue

        if np.nanstd(xa2) == 0 or np.nanstd(ya2) == 0:
            corrs.append(None)
            continue

        c = np.corrcoef(xa2, ya2)[0, 1]
        corrs.append(_finite_or_none(c))

    overlap0 = overlaps[lags.index(0)] if 0 in lags else 0
    overlap0 = max(int(overlap0), 1)

    best_idx: Optional[int] = None
    best_score = -1.0
    best_abs = -1.0

    for i, c in enumerate(corrs):
        if c is None:
            continue

        ov = overlaps[i]
        if ov < int(min_overlap):
            continue

        penalty = float(np.sqrt(ov / overlap0))
        score = abs(float(c)) * penalty

        if score > best_score:
            best_score = score
            best_abs = abs(float(c))
            best_idx = i

    best = {
        "lag": int(lags[best_idx]) if best_idx is not None else None,
        "correlation": corrs[best_idx] if best_idx is not None else None,
        "max_abs_correlation": _finite_or_none(best_abs) if best_idx is not None else None,
        "overlap_n": overlaps[best_idx] if best_idx is not None else None,
        "score": _finite_or_none(best_score) if best_idx is not None else None,
        "overlap_n_lag0": int(overlap0),
    }

    return {
        "lags": lags,
        "correlations": corrs,
        "overlap_n": overlaps,
        "best": best,
    }