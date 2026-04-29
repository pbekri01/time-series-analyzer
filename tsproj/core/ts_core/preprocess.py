from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict


def align_many_on_entity_year(
    dfs: Dict[str, pd.DataFrame],
    entity_col: str = "Entity",
    time_col: str = "Year",
) -> pd.DataFrame:
    """
    Align multiple time-series DataFrames on (entity, year) using OUTER JOIN.

    Keeps the full timeline for all series.
    Missing values are preserved as NaN and handled later during pairwise analysis.
    """
    aligned = None

    for name, df in dfs.items():
        df = df.copy()

        if entity_col not in df.columns:
            raise ValueError(f"{name} missing column '{entity_col}'")

        if time_col not in df.columns:
            raise ValueError(f"{name} missing column '{time_col}'")

        value_cols = [c for c in df.columns if c not in {entity_col, time_col, "Code"}]
        if len(value_cols) != 1:
            raise ValueError(
                f"{name} must contain exactly one value column besides Entity/Year"
            )

        value_col = value_cols[0]

        df = df[[entity_col, time_col, value_col]].rename(columns={value_col: name})
        df[name] = pd.to_numeric(df[name], errors="coerce")

        if aligned is None:
            aligned = df
        else:
            aligned = pd.merge(aligned, df, on=[entity_col, time_col], how="outer")

    aligned = aligned.sort_values([entity_col, time_col]).reset_index(drop=True)
    return aligned


def zscore(series: pd.Series) -> pd.Series:
    """
    Z-score normalization ignoring NaNs, without RuntimeWarnings.

    If there are no finite values, returns all-NaN.
    If std is zero (or not finite), returns all-NaN.
    """
    s = pd.to_numeric(series, errors="coerce").astype(float)

    # ✅ avoid "Mean of empty slice"
    finite = np.isfinite(s.to_numpy(dtype=float))
    if not np.any(finite):
        return s * np.nan

    mean = float(np.mean(s.to_numpy(dtype=float)[finite]))
    std = float(np.std(s.to_numpy(dtype=float)[finite]))

    # ✅ avoid "Degrees of freedom <= 0" and divide-by-zero
    if std == 0.0 or not np.isfinite(std):
        return s * np.nan

    return (s - mean) / std