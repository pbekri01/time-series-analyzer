from __future__ import annotations
import numpy as np
from typing import Dict

def moments4(x: np.ndarray) -> Dict[str, float]:
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return {"mean": float("nan"), "variance": float("nan"), "skewness": float("nan"), "kurtosis": float("nan")}
    mu = float(np.mean(x))
    var = float(np.var(x))
    sd = float(np.std(x))
    if sd == 0:
        return {"mean": mu, "variance": var, "skewness": 0.0, "kurtosis": 3.0}  # normal-like default
    m3 = float(np.mean(((x - mu) / sd) ** 3))
    m4 = float(np.mean(((x - mu) / sd) ** 4))
    # Pearson kurtosis (Normal => 3). If θέλεις excess, κάνεις m4-3.
    return {"mean": mu, "variance": var, "skewness": m3, "kurtosis": m4}
