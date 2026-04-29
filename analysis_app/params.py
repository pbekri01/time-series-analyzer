from __future__ import annotations

import numpy as np
import pandas as pd


def _infer_entity_col(df: pd.DataFrame) -> str | None:
    """
    Try to find the entity column in a loaded series dataframe.
    """
    candidates = ["Entity", "entity", "Country", "country"]

    for col in candidates:
        if col in df.columns:
            return col

    return None


def _entity_lengths(dfs: dict) -> list[int]:
    """
    Collect per-entity lengths across all uploaded dataframes.
    We use per-entity counts instead of total dataframe length because
    total length is inflated when many countries/entities are present.
    """
    lengths: list[int] = []

    for _, df in dfs.items():
        if df is None or df.empty:
            continue

        entity_col = _infer_entity_col(df)

        if entity_col is None:
            # fallback: if no entity column exists, use full dataframe length
            lengths.append(len(df))
            continue

        counts = df.groupby(entity_col).size().tolist()
        lengths.extend(int(c) for c in counts if c and c > 0)

    return lengths


def infer_max_lag_from_data(dfs: dict) -> int:
    """
    Infer a conservative max_lag based on typical per-entity series length.
    """
    lengths = _entity_lengths(dfs)

    if not lengths:
        return 1

    n = int(np.median(lengths))

    # Conservative choice for annual public-health data:
    # keep lag small to avoid unstable correlations.
    inferred = n // 8

    return max(1, min(3, inferred))


def infer_min_points_from_data(dfs: dict, max_lag: int) -> int:
    """
    Infer min_points from typical per-entity length, not total dataframe size.
    """
    lengths = _entity_lengths(dfs)

    if not lengths:
        return max(8, max_lag + 2)

    n = int(np.median(lengths))

    # Require a reasonable fraction of each entity's time series,
    # but avoid being too aggressive.
    inferred = max(8, min(20, int(n * 0.5)))

    return max(inferred, max_lag + 2)