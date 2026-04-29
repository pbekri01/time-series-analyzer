from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from itertools import combinations
from typing import Dict, Any, List, Optional, Tuple

from .preprocess import align_many_on_entity_year, zscore
from .decompose import decompose_series
from .features import moments4
from .fft_tools import top_frequencies
from .xcorr import cross_correlation
from .stationarity import StationarityAnalyzer


AGGREGATE_ENTITIES = {
    "World",
    "Africa",
    "Asia",
    "Europe",
    "North America",
    "South America",
    "Oceania",
    "European Union",
    "High-income countries",
    "Upper-middle-income countries",
    "Lower-middle-income countries",
    "Low-income countries",
    "Low income",
    "Lower middle income",
    "Upper middle income",
    "High income",
}


def _build_meta(
    series_names: List[str],
    entity_col: str,
    time_col: str,
    normalization: str,
    max_lag: int,
    period: int,
    min_points: int,
) -> Dict[str, Any]:
    return {
        "series": series_names,
        "entity_col": entity_col,
        "time_col": time_col,
        "normalization": normalization,
        "max_lag": max_lag,
        "decomposition_period": period,
        "min_points": min_points,
        "stationarity_enabled": True,
        "warnings": [],
    }


def _build_series_stationarity_map(
    series_names: List[str],
    g: pd.DataFrame,
    X_raw: Dict[str, np.ndarray],
    finite_counts: Dict[str, int],
    raw_series_map: Dict[str, pd.Series],
    stationarity_analyzer: StationarityAnalyzer,
    normalization: str,
) -> Dict[str, Any]:
    series_stationarity_map: Dict[str, Any] = {}

    for s in series_names:
        raw_vals = pd.to_numeric(g[s], errors="coerce").astype(float)
        raw_series_map[s] = raw_vals

        if normalization == "zscore":
            vals = zscore(raw_vals)
        else:
            vals = raw_vals

        arr = vals.to_numpy(dtype=float)
        X_raw[s] = arr
        finite_counts[s] = int(np.sum(np.isfinite(arr)))

        finite_arr = arr[np.isfinite(arr)]
        st = stationarity_analyzer.analyze(finite_arr, use_log=False)

        series_stationarity_map[s] = {
            "original_p_value": st.original_p_value,
            "final_p_value": st.final_p_value,
            "is_stationary_original": st.is_stationary_original,
            "is_stationary_final": st.is_stationary_final,
            "diffs_applied": st.diffs_applied,
            "transform_applied": st.transform_applied,
            "success": st.success,
            "reason": st.reason,
            "original_length": int(len(finite_arr)),
            "final_length": int(len(st.series_transformed)),
        }

    return series_stationarity_map


def _build_series_block(
    series_names: List[str],
    X_raw: Dict[str, np.ndarray],
    finite_counts: Dict[str, int],
    series_stationarity_map: Dict[str, Any],
    min_points: int,
    period: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    series_block: Dict[str, Any] = {}
    decomps: Dict[str, Any] = {}

    for s in series_names:
        y = X_raw[s]
        fc = finite_counts[s]
        moments_orig = moments4(y)

        if fc < int(min_points):
            series_block[s] = {
                "moments_original": moments_orig,
                "moments_residual": None,
                "fft_original_top10": top_frequencies(y, top_n=10, d=1.0),
                "fft_residual_top10": {"frequencies": [], "powers": []},
                "stationarity": series_stationarity_map.get(s),
                "warnings": [
                    f"Series '{s}' has only {fc} finite points (< min_points={min_points}); residual/trend skipped."
                ],
            }
            decomps[s] = None
            continue

        dres = decompose_series(y, period=period)
        decomps[s] = dres

        series_block[s] = {
            "moments_original": moments_orig,
            "moments_residual": moments4(dres.resid),
            "fft_original_top10": top_frequencies(y, top_n=10, d=1.0),
            "fft_residual_top10": top_frequencies(dres.resid, top_n=10, d=1.0),
            "stationarity": series_stationarity_map.get(s),
        }

    return series_block, decomps


def _analyze_pair(
    a: str,
    b: str,
    X_raw: Dict[str, np.ndarray],
    g: pd.DataFrame,
    time_col: str,
    entity: Any,
    stationarity_analyzer: StationarityAnalyzer,
    max_lag: int,
    min_points: int,
    period: int,
    series_block: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[float], bool, Optional[str]]:
    ya_raw = X_raw[a]
    yb_raw = X_raw[b]

    ya_overlap, yb_overlap, overlap_years = _pairwise_finite_overlap(
        years=g[time_col].astype(int).tolist(),
        x=ya_raw,
        y=yb_raw,
    )
    overlap0 = int(len(ya_overlap))

    if overlap0 == 0:
        return None, None, False, None

    low_overlap = overlap0 < int(min_points)
    low_overlap_warning = None

    if low_overlap:
        low_overlap_warning = (
            f"Low overlap for pair '{a}' vs '{b}' in entity '{entity}': "
            f"overlap_n_lag0={overlap0} (< min_points={min_points}). "
            f"Correlations may be None/unreliable."
        )

    raw_corr0, raw_pval0 = _corr_with_pvalue(ya_overlap, yb_overlap)
    raw_corr0_strength = abs(raw_corr0) if isinstance(raw_corr0, (int, float)) else 0.0

    st_a = stationarity_analyzer.analyze(ya_overlap, use_log=False)
    st_b = stationarity_analyzer.analyze(yb_overlap, use_log=False)

    ya = st_a.series_transformed
    yb = st_b.series_transformed

    n_pair = min(len(ya), len(yb))
    if n_pair == 0:
        return None, None, low_overlap, low_overlap_warning

    ya = ya[-n_pair:]
    yb = yb[-n_pair:]

    ccf = cross_correlation(ya, yb, max_lag=max_lag, min_overlap=min_points)

    corr0, pval0 = _corr_with_pvalue(ya, yb)
    corr0_strength = abs(corr0) if isinstance(corr0, (int, float)) else 0.0

    diff_corr, pval_diff = _corr_with_pvalue(np.diff(ya), np.diff(yb))
    diff_strength = abs(diff_corr) if isinstance(diff_corr, (int, float)) else 0.0
    diff_supports = diff_strength >= 0.50

    trend_corr = None
    resid_corr = None

    if n_pair >= int(min_points):
        da = decompose_series(ya, period=period)
        db = decompose_series(yb, period=period)
        trend_corr = _safe_corr(da.trend, db.trend)
        resid_corr = _safe_corr(da.resid, db.resid)

    trend_strength = abs(trend_corr) if isinstance(trend_corr, (int, float)) else 0.0
    resid_strength = abs(resid_corr) if isinstance(resid_corr, (int, float)) else 0.0

    trend_driven = (trend_strength >= 0.70) and (diff_strength < 0.30)
    spurious_risk = (
        (raw_corr0_strength > 0.90 and (raw_pval0 is None or raw_pval0 > 0.05))
        or
        (corr0_strength > 0.90 and (pval0 is None or pval0 > 0.05 or diff_strength < 0.30))
    )

    fa = (series_block[a].get("fft_original_top10") or {}).get("frequencies") or []
    fb = (series_block[b].get("fft_original_top10") or {}).get("frequencies") or []
    season_overlap = _seasonality_overlap_by_period(
        fa,
        fb,
        rel_tol=0.10,
        min_freq=1e-3,
    )

    pair_stationarity = {
        "series_A": {
            "original_p_value": st_a.original_p_value,
            "final_p_value": st_a.final_p_value,
            "is_stationary_original": st_a.is_stationary_original,
            "is_stationary_final": st_a.is_stationary_final,
            "diffs_applied": st_a.diffs_applied,
            "transform_applied": st_a.transform_applied,
            "success": st_a.success,
            "reason": st_a.reason,
            "original_length": int(len(ya_overlap)),
            "final_length": int(len(st_a.series_transformed)),
        },
        "series_B": {
            "original_p_value": st_b.original_p_value,
            "final_p_value": st_b.final_p_value,
            "is_stationary_original": st_b.is_stationary_original,
            "is_stationary_final": st_b.is_stationary_final,
            "diffs_applied": st_b.diffs_applied,
            "transform_applied": st_b.transform_applied,
            "success": st_b.success,
            "reason": st_b.reason,
            "original_length": int(len(yb_overlap)),
            "final_length": int(len(st_b.series_transformed)),
        },
    }

    pair_result = {
        "series_A": a,
        "series_B": b,
        "overlap_n_lag0": int(overlap0),
        "overlap_year_range": (
            {
                "start": int(min(overlap_years)),
                "end": int(max(overlap_years)),
            }
            if overlap_years
            else None
        ),
        "raw_corr_lag0": raw_corr0,
        "raw_p_value": raw_pval0,
        "pearson_corr_lag0": corr0,
        "pearson_p_value": pval0,
        "diff_correlation": diff_corr,
        "diff_p_value": pval_diff,
        "diff_strength": float(diff_strength),
        "diff_supports_relation": bool(diff_supports),
        "cross_correlation": ccf,
        "trend_correlation": trend_corr,
        "residual_correlation": resid_corr,
        "trend_driven": bool(trend_driven),
        "trend_strength": float(trend_strength),
        "residual_strength": float(resid_strength),
        "spurious_risk": bool(spurious_risk),
        "seasonality_overlap": bool(season_overlap),
        "stationarity": pair_stationarity,
    }

    return pair_result, raw_corr0, low_overlap, low_overlap_warning


def _build_ranges_and_chart_data(
    g: pd.DataFrame,
    series_names: List[str],
    raw_series_map: Dict[str, pd.Series],
    time_col: str,
    normalization: str,
    period: int,
) -> Tuple[Optional[Dict[str, int]], Dict[str, Dict[str, int]], Optional[Dict[str, int]], Dict[str, Any]]:
    years = g[time_col].tolist()

    entity_range = None
    if years:
        entity_range = {
            "start": int(min(years)),
            "end": int(max(years)),
        }

    series_ranges: Dict[str, Dict[str, int]] = {}
    series_year_sets: List[set] = []

    for s in series_names:
        vals = pd.to_numeric(g[s], errors="coerce")
        mask = vals.notna()

        if mask.any():
            yrs = g.loc[mask, time_col].astype(int).tolist()
            series_ranges[s] = {
                "start": int(min(yrs)),
                "end": int(max(yrs)),
            }
            series_year_sets.append(set(yrs))

    overlap_range = None
    if series_year_sets:
        common_years = set.intersection(*series_year_sets)
        if common_years:
            overlap_range = {
                "start": int(min(common_years)),
                "end": int(max(common_years)),
            }

    chart_years: List[int] = []
    chart_series: Dict[str, Dict[str, Any]] = {}

    if overlap_range is not None:
        start_y = int(overlap_range["start"])
        end_y = int(overlap_range["end"])
        chart_mask = g[time_col].astype(int).between(start_y, end_y)
        chart_years = g.loc[chart_mask, time_col].astype(int).tolist()
    else:
        chart_mask = pd.Series([False] * len(g), index=g.index)

    for s in series_names:
        raw_vals = raw_series_map[s]

        if normalization == "zscore":
            norm_vals = zscore(raw_vals)
        else:
            norm_vals = raw_vals

        # decomposition πάνω στις raw τιμές
        y = raw_vals.to_numpy(dtype=float)

        try:
            dres = decompose_series(y, period=period)
            trend_vals = pd.Series(dres.trend, index=raw_vals.index)
            resid_vals = pd.Series(dres.resid, index=raw_vals.index)
        except Exception:
            trend_vals = pd.Series(np.nan, index=raw_vals.index)
            resid_vals = pd.Series(np.nan, index=raw_vals.index)

        # first difference
        diff_vals = raw_vals.diff()

        raw_chart = raw_vals.loc[chart_mask].to_numpy(dtype=float)
        norm_chart = norm_vals.loc[chart_mask].to_numpy(dtype=float)
        trend_chart = trend_vals.loc[chart_mask].to_numpy(dtype=float)
        resid_chart = resid_vals.loc[chart_mask].to_numpy(dtype=float)
        diff_chart = diff_vals.loc[chart_mask].to_numpy(dtype=float)

        chart_series[s] = {
            "years": [int(y) for y in chart_years],
            "raw_values": [_finite_or_none(v) for v in raw_chart.tolist()],
            "normalized_values": [_finite_or_none(v) for v in norm_chart.tolist()],
            "trend_values": [_finite_or_none(v) for v in trend_chart.tolist()],
            "residual_values": [_finite_or_none(v) for v in resid_chart.tolist()],
            "differenced_values": [_finite_or_none(v) for v in diff_chart.tolist()],
        }

    chart_data = {
        "years": [int(y) for y in chart_years],
        "normalization": normalization,
        "series": chart_series,
    }

    return entity_range, series_ranges, overlap_range, chart_data


def _analyze_entity(
    entity: Any,
    g: pd.DataFrame,
    series_names: List[str],
    time_col: str,
    normalization: str,
    stationarity_analyzer: StationarityAnalyzer,
    max_lag: int,
    period: int,
    min_points: int,
    overall_corrs: Dict[Tuple[str, str], List[Optional[float]]],
) -> Optional[Dict[str, Any]]:
    g = g.sort_values(time_col)

    ent_warnings: List[str] = []

    if len(g) < min_points:
        return None

    X_raw: Dict[str, np.ndarray] = {}
    finite_counts: Dict[str, int] = {}
    raw_series_map: Dict[str, pd.Series] = {}

    series_stationarity_map = _build_series_stationarity_map(
        series_names=series_names,
        g=g,
        X_raw=X_raw,
        finite_counts=finite_counts,
        raw_series_map=raw_series_map,
        stationarity_analyzer=stationarity_analyzer,
        normalization=normalization,
    )

    series_block, _ = _build_series_block(
        series_names=series_names,
        X_raw=X_raw,
        finite_counts=finite_counts,
        series_stationarity_map=series_stationarity_map,
        min_points=min_points,
        period=period,
    )

    pairs: List[Dict[str, Any]] = []
    n_pairs_total = 0
    n_pairs_low_overlap = 0

    for a, b in combinations(series_names, 2):
        n_pairs_total += 1

        pair_result, corr0, low_overlap, low_overlap_warning = _analyze_pair(
            a=a,
            b=b,
            X_raw=X_raw,
            g=g,
            time_col=time_col,
            entity=entity,
            stationarity_analyzer=stationarity_analyzer,
            max_lag=max_lag,
            min_points=min_points,
            period=period,
            series_block=series_block,
        )

        if low_overlap:
            n_pairs_low_overlap += 1
        if low_overlap_warning:
            ent_warnings.append(low_overlap_warning)
        if pair_result is None:
            continue

        overall_corrs.setdefault((a, b), []).append(corr0)
        pairs.append(pair_result)

    entity_range, series_ranges, overlap_range, chart_data = _build_ranges_and_chart_data(
        g=g,
        series_names=series_names,
        raw_series_map=raw_series_map,
        time_col=time_col,
        normalization=normalization,
        period=period,
    )

    return {
        "entity_range": entity_range,
        "series_ranges": series_ranges,
        "overlap_range": overlap_range,
        "warnings": ent_warnings,
        "pairwise_stats": {
            "n_pairs_total": int(n_pairs_total),
            "n_pairs_low_overlap": int(n_pairs_low_overlap),
        },
        "series": series_block,
        "pairwise_analysis": pairs,
        "chart_data": chart_data,
    }


def _build_overall_summary(
    overall_corrs: Dict[Tuple[str, str], List[Optional[float]]]
) -> Dict[str, Any]:
    overall: Dict[str, Any] = {"pairwise": {}}

    for (a, b), vals in overall_corrs.items():
        arr = np.array([v for v in vals if v is not None], dtype=float)
        arr = arr[np.isfinite(arr)]

        n = int(arr.size)
        mean_corr = _safe_mean(arr)
        median_corr = _safe_median(arr)

        pos = int(np.sum(arr > 0)) if n > 0 else 0
        neg = int(np.sum(arr < 0)) if n > 0 else 0
        zero = int(np.sum(arr == 0)) if n > 0 else 0

        overall["pairwise"][f"{a}__{b}"] = {
            "n_entities": n,
            "mean_corr_lag0": mean_corr,
            "median_corr_lag0": median_corr,
            "n_positive": pos,
            "n_negative": neg,
            "n_zero": zero,
            "pct_positive": _safe_ratio(pos, n),
            "pct_negative": _safe_ratio(neg, n),
        }

    return overall


def _build_cross_sectional_summary(
    wide: pd.DataFrame,
    series_names: List[str],
    entity_col: str,
    time_col: str,
    min_entities_per_year: int = 15,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"pairwise": {}}

    for a, b in combinations(series_names, 2):
        yearly_corrs: List[Dict[str, Any]] = []

        for year, gy in wide.groupby(time_col):
            sub = gy[[entity_col, a, b]].copy()
            sub[a] = pd.to_numeric(sub[a], errors="coerce")
            sub[b] = pd.to_numeric(sub[b], errors="coerce")
            sub = sub.dropna(subset=[a, b])

            if len(sub) < min_entities_per_year:
                continue

            if sub[a].std() == 0 or sub[b].std() == 0:
                continue

            corr, pval = _corr_with_pvalue(
                sub[a].to_numpy(dtype=float),
                sub[b].to_numpy(dtype=float),
            )

            if corr is not None:
                yearly_corrs.append({
                    "year": int(year),
                    "corr": corr,
                    "p_value": pval,
                    "n_entities": int(len(sub)),
                })

        vals = np.array([x["corr"] for x in yearly_corrs if x["corr"] is not None], dtype=float)
        vals = vals[np.isfinite(vals)]

        if vals.size > 0:
            out["pairwise"][f"{a}__{b}"] = {
                "mean_corr": _finite_or_none(np.mean(vals)),
                "median_corr": _finite_or_none(np.median(vals)),
                "std_corr": _finite_or_none(np.std(vals)),
                "n_years": int(vals.size),
                "n_positive": int(np.sum(vals > 0)),
                "n_negative": int(np.sum(vals < 0)),
                "pct_positive": _safe_ratio(int(np.sum(vals > 0)), int(vals.size)),
                "pct_negative": _safe_ratio(int(np.sum(vals < 0)), int(vals.size)),
                "yearly": yearly_corrs,
            }
        else:
            out["pairwise"][f"{a}__{b}"] = {
                "mean_corr": None,
                "median_corr": None,
                "std_corr": None,
                "n_years": 0,
                "n_positive": 0,
                "n_negative": 0,
                "pct_positive": None,
                "pct_negative": None,
                "yearly": [],
            }

    return out


def analyze_many(
    dfs: Dict[str, pd.DataFrame],
    entity_col: str = "Entity",
    time_col: str = "Year",
    max_lag: int = 10,
    period: int = 1,
    min_points: int = 8,
    normalization: str = "zscore",
) -> Dict[str, Any]:
    """
    Returns prompt-ready dict (JSON-safe: no NaN/Inf):
    {
      "entities": { entity: {...} },
      "meta": {...},
      "overall": {...},
      "cross_sectional": {...}
    }

    Design
    ------
    - Series-level blocks remain descriptive and are built from each normalized series.
    - Pairwise analysis is computed ONLY on the common finite overlap of the pair.
    - Stationarity is checked pairwise on that common overlap, then transformed series
      are used for pairwise correlation / lag / trend-residual analysis.
    - Additionally, cross-sectional correlations are computed per year across entities.
    """
    wide = align_many_on_entity_year(dfs, entity_col=entity_col, time_col=time_col)
    stationarity_analyzer = StationarityAnalyzer(alpha=0.05, max_diffs=2)

    if entity_col in wide.columns:
        wide = wide[~wide[entity_col].isin(AGGREGATE_ENTITIES)].copy()

        counts = wide.groupby(entity_col)[time_col].nunique()
        valid_entities = counts[counts >= max(min_points, 8)].index
        removed_entities = set(wide[entity_col].unique()) - set(valid_entities)

        wide = wide[wide[entity_col].isin(valid_entities)].copy()
    else:
        removed_entities = set()

    series_names = [c for c in wide.columns if c not in {entity_col, time_col}]
    out: Dict[str, Any] = {
        "meta": _build_meta(
            series_names=series_names,
            entity_col=entity_col,
            time_col=time_col,
            normalization=normalization,
            max_lag=max_lag,
            period=period,
            min_points=min_points,
        ),
        "entities": {},
    }

    overall_corrs: Dict[Tuple[str, str], List[Optional[float]]] = {}

    if removed_entities:
        out["meta"]["warnings"].append(
            f"Filtered out {len(removed_entities)} aggregate/short entities before analysis."
        )

    if len(series_names) < 2:
        out["meta"]["warnings"].append(
            "Only one (or zero) series detected after alignment; pairwise analysis will be empty."
        )

    for entity, g in wide.groupby(entity_col):
        entity_result = _analyze_entity(
            entity=entity,
            g=g,
            series_names=series_names,
            time_col=time_col,
            normalization=normalization,
            stationarity_analyzer=stationarity_analyzer,
            max_lag=max_lag,
            period=period,
            min_points=min_points,
            overall_corrs=overall_corrs,
        )

        if entity_result is None:
            continue

        out["entities"][entity] = entity_result

    out["overall"] = _build_overall_summary(overall_corrs)
    out["cross_sectional"] = _build_cross_sectional_summary(
        wide=wide,
        series_names=series_names,
        entity_col=entity_col,
        time_col=time_col,
        min_entities_per_year=15,
    )
    cross_sectional_pairs = (out.get("cross_sectional") or {}).get("pairwise") or {}
    if cross_sectional_pairs and all((pair_data.get("n_years") or 0) == 0 for pair_data in cross_sectional_pairs.values()):
        out["meta"]["warnings"].append(
            "No yearly cross-sectional data were available. This usually means there were not enough entities with valid values in the same year to compute yearly correlations."
        )

    if out["entities"]:
        n_ent = len(out["entities"])
        n_ent_with_warn = sum(1 for e in out["entities"].values() if (e.get("warnings") or []))
        if n_ent_with_warn > 0:
            out["meta"]["warnings"].append(
                f"{n_ent_with_warn}/{n_ent} entities produced warnings (often due to low overlap)."
            )

    return out


def _corr_with_pvalue(x: np.ndarray, y: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)

    n = min(len(x), len(y))
    if n < 3:
        return None, None

    x = x[-n:]
    y = y[-n:]

    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    if x.size < 3:
        return None, None

    if np.nanstd(x) < 1e-12 or np.nanstd(y) < 1e-12:
        return None, None

    try:
        corr, pval = pearsonr(x, y)
        return _finite_or_none(corr), _finite_or_none(pval)
    except Exception:
        return None, None


def _finite_or_none(x: Any) -> Optional[float]:
    try:
        fx = float(x)
    except Exception:
        return None
    return fx if np.isfinite(fx) else None


def _overlap_n(x: np.ndarray, y: np.ndarray) -> int:
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)

    n = min(len(x), len(y))
    if n == 0:
        return 0

    x = x[-n:]
    y = y[-n:]
    mask = np.isfinite(x) & np.isfinite(y)
    return int(np.sum(mask))


def _pairwise_finite_overlap(
    years: List[int],
    x: np.ndarray,
    y: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, List[int]]:
    """
    Returns x and y restricted to the exact same finite rows, preserving time order.
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)

    n = min(len(years), len(x), len(y))
    if n == 0:
        return np.array([], dtype=float), np.array([], dtype=float), []

    years_arr = np.asarray(years[-n:], dtype=int)
    x = x[-n:]
    y = y[-n:]

    mask = np.isfinite(x) & np.isfinite(y)

    return x[mask], y[mask], years_arr[mask].tolist()


def _safe_corr(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)

    n = min(len(x), len(y))
    if n < 2:
        return None

    x = x[-n:]
    y = y[-n:]

    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    if x.size < 2:
        return None

    if np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return None

    c = np.corrcoef(x, y)[0, 1]
    return _finite_or_none(c)


def _diff_corr(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    x = np.asarray(x, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)

    n = min(len(x), len(y))
    if n < 3:
        return None

    x = x[-n:]
    y = y[-n:]

    dx = np.diff(x)
    dy = np.diff(y)

    mask = np.isfinite(dx) & np.isfinite(dy)
    dx = dx[mask]
    dy = dy[mask]

    if dx.size < 2:
        return None

    if np.nanstd(dx) == 0 or np.nanstd(dy) == 0:
        return None

    c = np.corrcoef(dx, dy)[0, 1]
    return _finite_or_none(c)


def _safe_mean(arr: np.ndarray) -> Optional[float]:
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return _finite_or_none(np.mean(arr))


def _safe_median(arr: np.ndarray) -> Optional[float]:
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return _finite_or_none(np.median(arr))


def _safe_ratio(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return _finite_or_none(num / den)


def _seasonality_overlap_by_period(
    freqs_a: List[Any],
    freqs_b: List[Any],
    rel_tol: float = 0.10,
    min_freq: float = 1e-3,
) -> bool:
    fa: List[float] = []
    fb: List[float] = []

    for f in freqs_a or []:
        fx = _finite_or_none(f)
        if fx is None or fx <= min_freq:
            continue
        fa.append(float(fx))

    for f in freqs_b or []:
        fx = _finite_or_none(f)
        if fx is None or fx <= min_freq:
            continue
        fb.append(float(fx))

    if not fa or not fb:
        return False

    pa = [1.0 / f for f in fa if f != 0.0]
    pb = [1.0 / f for f in fb if f != 0.0]

    for p1 in pa:
        for p2 in pb:
            denom = max(p1, p2)
            if denom <= 0:
                continue
            if abs(p1 - p2) / denom <= rel_tol:
                return True

    return False