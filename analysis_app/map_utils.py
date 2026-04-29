from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px


NON_COUNTRY_ENTITIES = {
    "Africa",
    "Asia",
    "Europe",
    "Americas",
    "North America",
    "South America",
    "Oceania",
    "World",
}


COUNTRY_NAME_MAP = {
    "Russian Federation": "Russia",
    "Czechia": "Czech Republic",
    "Kyrgyz Republic": "Kyrgyzstan",
    "Slovak Republic": "Slovakia",
    "Republic of Moldova": "Moldova",
    "Syrian Arab Republic": "Syria",
    "Viet Nam": "Vietnam",
    "Iran": "Iran",
    "Korea, Rep.": "South Korea",
    "Korea, Dem. People’s Rep.": "North Korea",
    "Lao PDR": "Laos",
    "Yemen, Rep.": "Yemen",
    "Egypt, Arab Rep.": "Egypt",
    "Turkiye": "Turkey",
}


def _format_pvalue(v: Any) -> str:
    if v is None:
        return "N/A"

    if isinstance(v, str):
        return v

    try:
        fv = float(v)
    except Exception:
        return str(v)

    if fv < 1e-4:
        return "<1e-4"
    return f"{fv:.4f}"


def _normalize(value: Any) -> str:
    return str(value).strip().lower()


def _pair_matches(
    pair: Dict[str, Any],
    series_A: Optional[str],
    series_B: Optional[str],
) -> bool:
    if not series_A or not series_B:
        return True

    pair_a = pair.get("series_A")
    pair_b = pair.get("series_B")

    if not pair_a or not pair_b:
        return False

    sa = _normalize(series_A)
    sb = _normalize(series_B)
    pa = _normalize(pair_a)
    pb = _normalize(pair_b)

    return (sa == pa and sb == pb) or (sa == pb and sb == pa)


def _pick_pair(
    pairs: List[Dict[str, Any]],
    series_A: Optional[str] = None,
    series_B: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not pairs:
        return None

    if series_A and series_B:
        for pair in pairs:
            if _pair_matches(pair, series_A, series_B):
                return pair
        return None

    return pairs[0]


def extract_available_pairs(analysis_result: Dict[str, Any]) -> List[Dict[str, str]]:
    entities = analysis_result.get("entities", {}) or {}
    seen: set[Tuple[str, str]] = set()
    results: List[Dict[str, str]] = []

    for entity_name, entity_payload in entities.items():
        if entity_name in NON_COUNTRY_ENTITIES:
            continue

        pairs = entity_payload.get("pairwise_analysis", []) or []
        for pair in pairs:
            x = pair.get("series_A")
            y = pair.get("series_B")

            if not x or not y:
                continue

            key = tuple(sorted((str(x), str(y))))
            if key in seen:
                continue

            seen.add(key)
            results.append(
                {
                    "x": str(x),
                    "y": str(y),
                    "label": f"{x} vs {y}",
                }
            )

    results.sort(key=lambda item: item["label"].lower())
    return results


def build_map_rows(
    analysis_result: Dict[str, Any],
    series_A: Optional[str] = None,
    series_B: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    entities = analysis_result.get("entities", {}) or {}
    for entity_name, entity_payload in entities.items():
        if entity_name in NON_COUNTRY_ENTITIES:
            continue

        pairs = entity_payload.get("pairwise_analysis", []) or []
        if not pairs:
            continue

        p = _pick_pair(pairs, series_A=series_A, series_B=series_B)
        if not p:
            continue

        country_name = COUNTRY_NAME_MAP.get(entity_name, entity_name)
        overlap = p.get("overlap_year_range") or {}

        pair_a = p.get("series_A")
        pair_b = p.get("series_B")
        best = (p.get("cross_correlation") or {}).get("best") or {}


        rows.append(
            {
                "entity": country_name,
                "source_entity": entity_name,
                "pair_label": f"{pair_a or 'Unknown'} vs {pair_b or 'Unknown'}",
                "x_column": pair_a,
                "y_column": pair_b,
                "corr_lag0": p.get("pearson_corr_lag0"),
                "max_abs_corr": best.get("max_abs_correlation"),
                "best_lag": best.get("lag"),
                "best_overlap_n": best.get("overlap_n"),
                "pearson_p_value": p.get("pearson_p_value"),
                "diff_corr": p.get("diff_correlation"),
                "diff_p_value": p.get("diff_p_value"),
                "residual_corr": p.get("residual_correlation"),
                "trend_corr": p.get("trend_correlation"),
                "trend_driven": p.get("trend_driven"),
                "spurious_risk": p.get("spurious_risk"),
                "overlap_start": overlap.get("start"),
                "overlap_end": overlap.get("end"),
                "is_significant": (
                    (
                        isinstance(p.get("pearson_p_value"), (int, float))
                        and p.get("pearson_p_value") < 0.05
                    )
                    or p.get("pearson_p_value") == "<1e-4"
                ),
            }
        )

    return rows



def build_choropleth_html(
    map_rows: List[Dict[str, Any]],
    metric: str = "diff_corr",
    significant_only: bool = False,
) -> str:
    if not map_rows:
        return "<div class='muted'>No map data available yet.</div>"

    df = pd.DataFrame(map_rows)

    if significant_only and "is_significant" in df.columns:
        df = df[df["is_significant"] == True].copy()

    if metric not in df.columns:
        return "<div class='muted'>Requested map metric is not available.</div>"

    df = df[df[metric].notna()].copy()
    if df.empty:
        return "<div class='muted'>No mappable values available for the selected metric.</div>"

    df["pearson_p_value_display"] = df["pearson_p_value"].apply(_format_pvalue)
    df["diff_p_value_display"] = df["diff_p_value"].apply(_format_pvalue)
    df["overlap_display"] = df.apply(
        lambda r: (
            f"{int(r['overlap_start'])}-{int(r['overlap_end'])}"
            if pd.notna(r["overlap_start"]) and pd.notna(r["overlap_end"])
            else "N/A"
        ),
        axis=1,
    )

    color_scale = "RdBu"
    color_range = (-1, 1)

    if metric == "max_abs_corr":
        color_scale = "Viridis"
        color_range = (0, 1)

    fig = px.choropleth(
        df,
        locations="entity",
        locationmode="country names",
        color=metric,
        hover_name="entity",
        custom_data=["source_entity", "x_column", "y_column"],
        hover_data={
            "pair_label": True,
            "corr_lag0": True,
            "max_abs_corr": True,
            "best_lag": True,
            "best_overlap_n": True,
            "pearson_p_value_display": True,
            "diff_corr": True,
            "diff_p_value_display": True,
            "residual_corr": True,
            "trend_corr": True,
            "trend_driven": True,
            "spurious_risk": True,
            "overlap_display": True,
            "entity": False,
            "source_entity": False,
            "x_column": False,
            "y_column": False,
            "pearson_p_value": False,
            "diff_p_value": False,
            "overlap_start": False,
            "overlap_end": False,
            "is_significant": False,
        },
        color_continuous_scale=color_scale,
        range_color=color_range,
    )

    fig.update_geos(
        showframe=False,
        showcoastlines=True,
        projection_type="equirectangular",
        showcountries=True,
    )

    fig.update_layout(
        margin=dict(l=0, r=0, t=20, b=0),
        height=560,
        coloraxis_colorbar_title=metric,
    )

    return fig.to_html(full_html=False, include_plotlyjs=False, div_id="analysis-map")