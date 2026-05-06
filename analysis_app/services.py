import os
import tempfile

from .params import infer_max_lag_from_data, infer_min_points_from_data
from .prompt_builder import build_llm_prompt

from tsproj.core.ts_core.io import load_csv_series
from tsproj.core.ts_core.pipeline import analyze_many

from .exports import _overlap_n_from_range


def load_uploaded_csvs(uploaded_files):
    """
    Saves uploaded files temporarily and loads them as pandas DataFrames.

    If multiple uploaded CSVs resolve to the same series name, suffixes are added:
    e.g. Value, Value_2, Value_3
    """
    dfs = {}
    tmp_paths = []

    try:
        for f in uploaded_files:
            suffix = os.path.splitext(f.name)[-1] or ".csv"

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

            for chunk in f.chunks():
                tmp.write(chunk)

            tmp.close()
            tmp_paths.append(tmp.name)

            df, spec = load_csv_series(tmp.name)
            df = df.rename(columns={spec.value_col: spec.name})

            name = spec.name
            counter = 2

            while name in dfs:
                name = f"{spec.name}_{counter}"
                counter += 1

            df = df.rename(columns={spec.name: name})
            dfs[name] = df

        return dfs

    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except OSError:
                pass


def run_analysis(dfs, params):
    """
    Runs the core time-series analysis.
    """
    max_lag = infer_max_lag_from_data(dfs)
    min_points = infer_min_points_from_data(dfs, max_lag=max_lag)

    result = analyze_many(
        dfs,
        max_lag=max_lag,
        period=params["period"],
        min_points=min_points,
        normalization=params["normalization"],
    )

    result.setdefault("meta", {})
    result["meta"]["max_lag"] = max_lag
    result["meta"]["min_points"] = min_points
    result["meta"]["max_lag_auto"] = True
    result["meta"]["min_points_auto"] = True

    return result


def _pair_score_for_summary(p: dict) -> float:
    """
    Weighted score for ranking pairs in summaries.

    Preference order:
    - trend correlation
    - raw lag-0 correlation
    - best cross-correlation

    Penalizes spurious correlations.
    """
    trend = p.get("trend_correlation")
    raw = p.get("raw_corr_lag0")

    best = None
    cc = p.get("cross_correlation") or {}
    if isinstance(cc, dict):
        best_block = cc.get("best") or {}
        best = best_block.get("correlation")

    score = 0.0

    if isinstance(trend, (int, float)):
        score += 0.50 * abs(trend)

    if isinstance(raw, (int, float)):
        score += 0.30 * abs(raw)

    if isinstance(best, (int, float)):
        score += 0.20 * abs(best)

    if p.get("spurious_risk") is True:
        score *= 0.35

    return float(score)


def make_summary_payload(result: dict, summary_top_pairs: int = 1) -> dict:
    meta = result.get("meta", {}) or {}
    entities = result.get("entities", {}) or {}
    overall = result.get("overall", {}) or {}
    if "pairwise" not in overall:
        overall["pairwise"] = {}
    cross_sectional = result.get("cross_sectional", {}) or {}

    if "warnings" not in meta or meta["warnings"] is None:
        meta["warnings"] = []

    summary_entities = {}
    valid_entities = []

    for ent_name, ent_data in entities.items():
        pairs = ent_data.get("pairwise_analysis", []) or []

        
        valid_pairs = [
            p for p in pairs
            if p.get("series_A") and p.get("series_B")
        ]

        if not valid_pairs:
            continue

        valid_entities.append(ent_name)

        pairs_sorted = sorted(
            valid_pairs,
            key=_pair_score_for_summary,
            reverse=True,
        )[:summary_top_pairs]

        compact_pairs = []
        for p in pairs_sorted:
            best = (p.get("cross_correlation") or {}).get("best") or {}

            compact_pairs.append({
                "series_A": p.get("series_A"),
                "series_B": p.get("series_B"),
                "overlap_n_lag0": p.get("overlap_n_lag0"),
                "best_overlap_n": best.get("overlap_n"),
                "best_lag": best.get("lag"),
                "best_corr": best.get("correlation"),
                "max_abs_corr": best.get("max_abs_correlation"),
                "raw_corr_lag0": p.get("raw_corr_lag0"),
                "raw_p_value": p.get("raw_p_value"),
                "corr_lag0": p.get("pearson_corr_lag0"),
                "pearson_p_value": p.get("pearson_p_value"),
                "trend_corr": p.get("trend_correlation"),
                "residual_corr": p.get("residual_correlation"),
                "diff_corr": p.get("diff_correlation"),
                "diff_p_value": p.get("diff_p_value"),
                "diff_supports": p.get("diff_supports_relation"),
                "spurious_risk": p.get("spurious_risk"),
                "trend_driven": p.get("trend_driven"),
                "trend_strength": p.get("trend_strength"),
                "residual_strength": p.get("residual_strength"),
                # "seasonality_overlap": p.get("seasonality_overlap"),
                "summary_score": _pair_score_for_summary(p),
            })

        overlap_range = ent_data.get("overlap_range")
        overlap_n = _overlap_n_from_range(overlap_range)

        summary_entities[ent_name] = {
            "entity_range": ent_data.get("entity_range"),
            "series_ranges": ent_data.get("series_ranges"),
            "overlap_range": overlap_range,
            "n_points": overlap_n,
            "warnings": ent_data.get("warnings", []) or [],
            "pairwise_stats": ent_data.get("pairwise_stats", {}) or {},
            "top_pairs": compact_pairs,
        }

    valid_entities.sort()

    return {
        "meta": meta,
        "entities": summary_entities,
        "valid_entities": valid_entities,
        "overall": overall,
        "cross_sectional": cross_sectional,
    }


def build_entity_response(result, params):
    """
    Extracts a single entity and optionally builds an LLM prompt.
    """
    requested_entity = params.get("entity")

    if not requested_entity:
        raise ValueError("return_mode='entity' requires 'entity' parameter.")

    ent = (result.get("entities") or {}).get(requested_entity)

    if ent is None:
        raise LookupError(f"Entity '{requested_entity}' not found.")

    payload = {
        "meta": result["meta"],
        "entities": {requested_entity: ent},
    }

    if "cross_sectional" in result:
        payload["cross_sectional"] = result["cross_sectional"]

    include_prompt = params.get("include_prompt", True)

    if include_prompt:
        payload["llm_prompt_entity"] = requested_entity
        payload["llm_prompt"] = build_llm_prompt(
            payload,
            requested_entity,
            specific_events=True,
            top_pairs=params.get("top_pairs", 10),
            top_freqs=params.get("top_freqs", 5),
        )

    return payload