import io
import csv
import json
import math
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional


def _safe_year_range_start_end(d: Optional[dict]) -> tuple[Optional[int], Optional[int]]:
    d = d or {}
    start = d.get("start")
    end = d.get("end")
    return start, end


def _overlap_n_from_range(overlap_range: Optional[dict]) -> Optional[int]:
    start, end = _safe_year_range_start_end(overlap_range)
    if start is None or end is None:
        return None
    try:
        return int(end) - int(start) + 1
    except Exception:
        return None


def _csv_safe_value(v: Any) -> str:
    """
    Force stable machine-friendly CSV values.

    Rules:
    - None / NaN / Inf -> ""
    - bool -> "true" / "false"
    - int -> normal integer string
    - float -> Python-style decimal/scientific notation with '.' decimal separator
    - everything else -> str(v)
    """
    if v is None:
        return ""

    if isinstance(v, bool):
        return "true" if v else "false"

    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)

    if isinstance(v, float):
        if not math.isfinite(v):
            return ""
        return format(v, ".15g")

    try:
        fv = float(v)
        if math.isfinite(fv):
            return format(fv, ".15g")
        return ""
    except Exception:
        return str(v)


def _sanitize_row_for_csv(row: dict) -> dict:
    return {k: _csv_safe_value(v) for k, v in row.items()}


def flatten_results_csv_rows(result: dict) -> list[dict]:
    """
    Flatten current pipeline output into CSV rows.

    Compatible with the updated result schema:
    - entities[entity].entity_range
    - entities[entity].overlap_range
    - entities[entity].pairwise_analysis[]
    - pairwise.cross_correlation.best
    - pairwise.stationarity.series_A / series_B
    """
    meta = result.get("meta") or {}
    entities = result.get("entities") or {}

    rows: list[dict] = []

    for ent_name, ent in entities.items():
        entity_range = ent.get("entity_range") or {}
        overlap_range = ent.get("overlap_range") or {}

        entity_start, entity_end = _safe_year_range_start_end(entity_range)
        overlap_start, overlap_end = _safe_year_range_start_end(overlap_range)
        overlap_n_points = _overlap_n_from_range(overlap_range)

        for p in (ent.get("pairwise_analysis") or []):
            best = (p.get("cross_correlation") or {}).get("best") or {}
            pair_stationarity = p.get("stationarity") or {}
            st_a = pair_stationarity.get("series_A") or {}
            st_b = pair_stationarity.get("series_B") or {}
            overlap_year_range = p.get("overlap_year_range") or {}

            pair_overlap_start, pair_overlap_end = _safe_year_range_start_end(overlap_year_range)

            rows.append({
                "entity": ent_name,

                "entity_start_year": entity_start,
                "entity_end_year": entity_end,

                "overlap_start_year": overlap_start,
                "overlap_end_year": overlap_end,
                "overlap_n_points": overlap_n_points,

                "pair_overlap_start_year": pair_overlap_start,
                "pair_overlap_end_year": pair_overlap_end,

                "series_A": p.get("series_A"),
                "series_B": p.get("series_B"),

                "overlap_n_lag0": p.get("overlap_n_lag0"),
                "best_overlap_n": best.get("overlap_n"),

                "best_lag": best.get("lag"),
                "best_corr": best.get("correlation"),
                "best_score": best.get("score"),
                "max_abs_corr": best.get("max_abs_correlation"),

                "corr_lag0": p.get("pearson_corr_lag0"),
                "trend_corr": p.get("trend_correlation"),
                "residual_corr": p.get("residual_correlation"),
                "diff_corr": p.get("diff_correlation"),
                "diff_supports_relation": p.get("diff_supports_relation"),
                "diff_strength": p.get("diff_strength"),

                "trend_driven": p.get("trend_driven"),
                "trend_strength": p.get("trend_strength"),
                "residual_strength": p.get("residual_strength"),

                "spurious_risk": p.get("spurious_risk"),
                "seasonality_overlap": p.get("seasonality_overlap"),

                "stationarity_A_original_p_value": st_a.get("original_p_value"),
                "stationarity_A_final_p_value": st_a.get("final_p_value"),
                "stationarity_A_is_stationary_original": st_a.get("is_stationary_original"),
                "stationarity_A_is_stationary_final": st_a.get("is_stationary_final"),
                "stationarity_A_diffs_applied": st_a.get("diffs_applied"),
                "stationarity_A_transform_applied": st_a.get("transform_applied"),
                "stationarity_A_success": st_a.get("success"),
                "stationarity_A_original_length": st_a.get("original_length"),
                "stationarity_A_final_length": st_a.get("final_length"),

                "stationarity_B_original_p_value": st_b.get("original_p_value"),
                "stationarity_B_final_p_value": st_b.get("final_p_value"),
                "stationarity_B_is_stationary_original": st_b.get("is_stationary_original"),
                "stationarity_B_is_stationary_final": st_b.get("is_stationary_final"),
                "stationarity_B_diffs_applied": st_b.get("diffs_applied"),
                "stationarity_B_transform_applied": st_b.get("transform_applied"),
                "stationarity_B_success": st_b.get("success"),
                "stationarity_B_original_length": st_b.get("original_length"),
                "stationarity_B_final_length": st_b.get("final_length"),

                "normalization": meta.get("normalization"),
                "max_lag": meta.get("max_lag"),
                "min_points": meta.get("min_points"),
                "decomposition_period": meta.get("decomposition_period"),
                "stationarity_enabled": meta.get("stationarity_enabled"),
                "max_lag_auto": meta.get("max_lag_auto"),
                "min_points_auto": meta.get("min_points_auto"),
            })

    return rows


def make_export_zip_bytes(result: dict) -> bytes:
    """
    Creates a ZIP export containing:
    - results.csv          -> flattened pairwise rows
    - run_metadata.json    -> export/run metadata
    - summary.json         -> full result payload
    """
    meta = result.get("meta") or {}
    entities = result.get("entities") or {}

    generated_at = datetime.now(timezone.utc).isoformat()

    run_metadata = {
        "generated_at_utc": generated_at,
        "meta": meta,
        "counts": {
            "n_entities": len(entities),
            "n_series": len(meta.get("series") or []),
            "n_pairs_total": sum(
                (e.get("pairwise_stats") or {}).get("n_pairs_total", 0)
                for e in entities.values()
            ),
            "n_pairs_low_overlap": sum(
                (e.get("pairwise_stats") or {}).get("n_pairs_low_overlap", 0)
                for e in entities.values()
            ),
        },
        "export_schema_version": 3,
    }

    rows = flatten_results_csv_rows(result)

    fieldnames = [
        "entity",

        "entity_start_year",
        "entity_end_year",

        "overlap_start_year",
        "overlap_end_year",
        "overlap_n_points",

        "pair_overlap_start_year",
        "pair_overlap_end_year",

        "series_A",
        "series_B",

        "overlap_n_lag0",
        "best_overlap_n",

        "best_lag",
        "best_corr",
        "best_score",
        "max_abs_corr",

        "corr_lag0",
        "trend_corr",
        "residual_corr",
        "diff_corr",
        "diff_supports_relation",
        "diff_strength",

        "trend_driven",
        "trend_strength",
        "residual_strength",

        "spurious_risk",
        "seasonality_overlap",

        "stationarity_A_original_p_value",
        "stationarity_A_final_p_value",
        "stationarity_A_is_stationary_original",
        "stationarity_A_is_stationary_final",
        "stationarity_A_diffs_applied",
        "stationarity_A_transform_applied",
        "stationarity_A_success",
        "stationarity_A_original_length",
        "stationarity_A_final_length",

        "stationarity_B_original_p_value",
        "stationarity_B_final_p_value",
        "stationarity_B_is_stationary_original",
        "stationarity_B_is_stationary_final",
        "stationarity_B_diffs_applied",
        "stationarity_B_transform_applied",
        "stationarity_B_success",
        "stationarity_B_original_length",
        "stationarity_B_final_length",

        "normalization",
        "max_lag",
        "min_points",
        "decomposition_period",
        "stationarity_enabled",
        "max_lag_auto",
        "min_points_auto",
    ]

    csv_buf = io.StringIO()
    writer = csv.DictWriter(
        csv_buf,
        fieldnames=fieldnames,
        extrasaction="ignore",
        delimiter=",",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()

    for row in rows:
        writer.writerow(_sanitize_row_for_csv(row))

    csv_bytes = csv_buf.getvalue().encode("utf-8")
    meta_bytes = json.dumps(run_metadata, ensure_ascii=False, indent=2).encode("utf-8")
    summary_bytes = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("run_metadata.json", meta_bytes)
        zf.writestr("summary.json", summary_bytes)

    return zbuf.getvalue()