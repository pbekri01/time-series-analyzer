from __future__ import annotations
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

@dataclass(frozen=True)
class SeriesSpec:
    name: str
    value_col: str
    entity_col: str = "Entity"
    time_col: str = "Year"
    code_col: str = "Code"

def _detect_value_column(df: pd.DataFrame) -> str:
    known = {"Entity", "Code", "Year"}
    candidates = [c for c in df.columns if c not in known]
    if not candidates:
        raise ValueError("No value column detected.")

    best = None
    best_score = -1
    for c in candidates:
        s = pd.to_numeric(df[c], errors="coerce")
        score = s.notna().sum()
        if score > best_score:
            best_score = score
            best = c

    if best is None:
        raise ValueError("Could not detect a numeric value column.")
    return best

def load_csv_series(
    file_path: str,
    series_name: Optional[str] = None,
) -> Tuple[pd.DataFrame, SeriesSpec]:

    df = pd.read_csv(file_path)

    for col in ["Entity", "Year"]:
        if col not in df.columns:
            raise ValueError(f"Invalid CSV format. Required columns: Entity, Year, and one numeric value column.")

    value_col = _detect_value_column(df)
    name = series_name or value_col
    spec = SeriesSpec(name=name, value_col=value_col)

    # Keep only relevant columns
    keep = [c for c in [spec.entity_col, spec.code_col, spec.time_col, spec.value_col] if c in df.columns]
    df = df[keep].copy()

    # Coerce types
    df[spec.time_col] = pd.to_numeric(df[spec.time_col], errors="coerce").astype("Int64")
    df[spec.value_col] = pd.to_numeric(df[spec.value_col], errors="coerce")

    # Drop invalid rows
    df = df.dropna(subset=[spec.entity_col, spec.time_col, spec.value_col])

    df[spec.time_col] = df[spec.time_col].astype(int)

    # Sort by time 
    df = df.sort_values([spec.entity_col, spec.time_col]).reset_index(drop=True)

    # Merge duplicates using MEAN
    key_cols = [spec.entity_col, spec.time_col]
    if df.duplicated(key_cols).any():
        agg = {spec.value_col: "mean"}
        if spec.code_col in df.columns:
            agg[spec.code_col] = "first"

        df = (
            df.groupby(key_cols, as_index=False)
              .agg(agg)
              .sort_values(key_cols)
              .reset_index(drop=True)
        )

    return df, spec

def load_many_csvs(
    paths: List[str],
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, SeriesSpec]]:

    dfs: Dict[str, pd.DataFrame] = {}
    specs: Dict[str, SeriesSpec] = {}

    for p in paths:
        df, spec = load_csv_series(p)

        key = spec.name
        if key in dfs:
            i = 2
            new_key = f"{key} ({i})"
            while new_key in dfs:
                i += 1
                new_key = f"{key} ({i})"
            key = new_key
            spec = SeriesSpec(
                name=key,
                value_col=spec.value_col,
                entity_col=spec.entity_col,
                time_col=spec.time_col,
                code_col=spec.code_col,
            )

        dfs[key] = df
        specs[key] = spec

    return dfs, specs
