from __future__ import annotations

import numpy as np
from typing import Dict, List, Optional, Any


def top_frequencies(x: np.ndarray, top_n: int = 10, d: float = 1.0) -> Dict[str, Any]:
    """
    Compute top frequencies using FFT.

    Safety:
    - If < 3 finite points -> return empty result (FFT not meaningful)
    - Avoid RuntimeWarnings from empty/NaN slices
    """
    x = np.asarray(x, dtype=float)

    finite = np.isfinite(x)
    xf = x[finite]

    if xf.size < 3:
        return {"frequencies": [], "powers": []}

    xf = xf - np.mean(xf)

    n = xf.size
    fft_vals = np.fft.rfft(xf)
    freqs = np.fft.rfftfreq(n, d=d)
    powers = np.abs(fft_vals) ** 2

    if freqs.size <= 1:
        return {"frequencies": [], "powers": []}

    # ignore zero frequency (trend/DC component)
    freqs = freqs[1:]
    powers = powers[1:]

    if freqs.size == 0:
        return {"frequencies": [], "powers": []}

    idx = np.argsort(powers)[::-1][:top_n]

    top_freqs = [float(freqs[i]) for i in idx if np.isfinite(freqs[i])]
    top_pows = [float(powers[i]) for i in idx if np.isfinite(powers[i])]

    return {"frequencies": top_freqs, "powers": top_pows}