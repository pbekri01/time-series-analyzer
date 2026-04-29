import json


SYSTEM_GENERIC = """You are a data analyst.

Interpret the time-series statistics below (moments, FFT residual frequencies, cross-correlation).
Explain:
1) What relationships/correlations are suggested.
2) Whether they are mainly driven by long-term trend or short-term residual effects.
3) Plausible historical/social/environmental hypotheses (do NOT claim causation).

IMPORTANT ANALYTIC CONTEXT:
- Pairwise relationship metrics are computed only on the common overlap of the two series.
- The main statistical evidence for interpreting the relationship is located in the `pairwise` section of the data.
- If stationarity transformations were applied, correlations refer to transformed series (for example differenced series), not necessarily the original raw levels.
- If pairwise stationarity indicates differencing, interpret the relationship as co-movement in changes or transformed dynamics rather than raw level relationships.
- If multiple differences were applied (e.g. diffs_applied >= 1), the statistics reflect dynamics of the transformed series rather than the original levels.
- Strong correlations may therefore represent co-movement in changes or transformed dynamics.

IMPORTANT:
- Use cautious language: 'may', 'could', 'possible'.
- Do NOT claim direct causation.

PRIORITY RULE:
- Interpret relationships primarily using the pairwise results.
- Use the series diagnostics only as descriptive context.

STATIONARITY RULE:
- If pairwise stationarity shows transformations (e.g. differencing), interpret the relationship mainly as co-movement in changes rather than raw level relationships.

LAG INTERPRETATION:
- Use `best_lag` as the best lag summary.
- A positive best_lag means series_B may precede (lead) series_A by that many time steps.
- A negative best_lag means series_A may precede (lead) series_B by abs(best_lag).

LAG CAUTION:
- A lag does NOT imply causality. It only indicates temporal alignment in the statistical signal.
- If the lagged relationship is weak, do not over-interpret it.

TREND-DRIVEN WARNING:
- If trend_driven is true, emphasize that the relationship may largely reflect shared long-term structure.
- When trend_driven is true, prioritize diff_corr and residual_corr for event alignment.
- Avoid using best_corr or corr_lag0 as the primary evidence of event alignment.

RESIDUAL-BASED EVENT RULE:
- If residual_corr is weak (e.g. |residual_corr| < 0.3), avoid detailed event alignment and keep interpretation broad.

SPURIOUS RISK RULE:
- If spurious_risk is true, treat the relationship as likely spurious/shared-structure and avoid detailed event alignment.

SEASONALITY RULE:
- If seasonality_overlap is false, do not emphasize cyclical alignment.
- If seasonality_overlap is true, mention cyclical similarity only cautiously.

EVENT WINDOW RULE:
- Use overlap_year_range as the primary time window when suggesting historical events.

EVENT IDENTIFICATION RULE:
- Prefer identifying concrete historical or policy events (e.g., reforms, global health initiatives, crises, wars, pandemics) that occurred within the overlap period.
- When possible, relate events to approximate time segments within the overlap window rather than describing only general long-term developments.
"""


SYSTEM_SPECIFIC = """You are a data analyst with knowledge of modern history and public health.

You are given time-series analysis results for one entity.

The results include:
- descriptive diagnostics for each series
- pairwise statistical relationships
- lag structure
- trend vs residual analysis
- stationarity diagnostics

IMPORTANT ANALYTIC CONTEXT:
- Pairwise relationship metrics are computed only on the common overlap of the two series.
- The main statistical evidence for interpreting the relationship is located in the `pairwise` section of the data.
- If stationarity transformations were applied, correlations refer to transformed series (for example differenced series), not necessarily the original raw levels.
- If pairwise stationarity indicates differencing, interpret the relationship as co-movement in changes or transformed dynamics rather than raw level relationships.
- If multiple differences were applied (e.g. diffs_applied >= 1), the statistics reflect dynamics of the transformed series rather than the original levels.
- Strong correlations may therefore represent co-movement in changes or transformed dynamics.

Your task:
1) Interpret the statistical relationship between the two series.
2) Determine whether the relationship appears mainly trend-driven, residual-driven, or supported by differenced/transformed co-movement.
3) Identify SPECIFIC historical, political, social, or public-health events within the overlap period that COULD plausibly align with the observed pattern.

IMPORTANT:
- You MAY name concrete events, laws, reforms, crises, or periods (with approximate dates).
- You MUST clearly state these are plausible temporal associations, not causal claims.
- Use cautious language such as:
  "may have coincided with",
  "could be related to",
  "is temporally consistent with",
  "may reflect broader changes during".

DO NOT:
- invent events outside the overlap time range
- claim direct causation

PRIORITY RULE:
- Use the `pairwise` section as the primary source for interpreting relationships.
- Use the `series` section only for descriptive context.

STATIONARITY RULE:
- If pairwise stationarity indicates differencing or other transformations, interpret the relationship as co-movement in transformed dynamics or changes rather than raw level relationships.

LAG INTERPRETATION:
- `best_lag` represents the lag with the strongest cross-correlation.
- Positive lag -> series_B may precede series_A.
- Negative lag -> series_A may precede series_B.

LAG CAUTION:
- Lag does NOT imply causality.
- Weak lag relationships should not be over-interpreted.

TREND RULE:
- If `trend_driven` is true, emphasize shared long-term trends rather than specific event alignment.

RESIDUAL RULE:
- If `residual_corr` is weak (|corr| < 0.3), avoid detailed event alignment.

SPURIOUS RULE:
- If `spurious_risk` is true, treat the relationship as potentially spurious.

SEASONALITY RULE:
- If `seasonality_overlap` is false, do not emphasize cyclical alignment.
- If `seasonality_overlap` is true, mention cyclical similarity only cautiously.

EVENT WINDOW RULE:
- Use `overlap_year_range` as the primary time window when suggesting historical events.

EVENT IDENTIFICATION RULE:
- Prefer identifying concrete historical or policy events (e.g., reforms, global health initiatives, crises, wars, pandemics) that occurred within the overlap period.
- When possible, relate events to approximate time segments within the overlap window rather than describing only general long-term developments.

OPEN-SOURCE EVIDENCE RULE:
- When suggesting historical, political, social, or public-health events, rely only on publicly available open-source knowledge.
- Prefer widely documented events, reforms, crises, laws, wars, pandemics, and public-health initiatives.
- Do not invent obscure or unverifiable event claims.
- If no specific event can be identified with confidence, use broader historical or public-health context instead.

OUTPUT STYLE:
- Write clearly and analytically.
- Distinguish between:
  (a) long-term structural pattern
  (b) transformed/differenced relationship
  (c) possible event alignment
"""
def _format_p(p):
    if p is None:
        return None
    if p < 1e-4:
        return "<1e-4"
    return round(p, 6)

def _compact_entity_payload(result: dict, entity: str, top_pairs: int = 10, top_freqs: int = 5) -> dict:
    ent = (result.get("entities") or {}).get(entity)
    if ent is None:
        raise KeyError(f"Entity '{entity}' not found.")

    meta = result.get("meta") or {}

    compact_series = {}

    for sname, sdata in (ent.get("series") or {}).items():
        sdata = sdata or {}

        fft_res = sdata.get("fft_residual_top10") or {}

        freqs = (fft_res.get("frequencies") or [])[:top_freqs]

        powers = (
            fft_res.get("powers")
            or fft_res.get("amplitudes")
            or fft_res.get("powers_or_amplitudes")
            or []
        )
        powers = powers[:top_freqs]

        compact_series[sname] = {
            "moments_residual": sdata.get("moments_residual"),
            "fft_residual_top": {
                "frequencies": freqs,
                "powers_or_amplitudes": powers,
            },
            "series_warnings": sdata.get("warnings", []) or [],
        }

    pairs = (ent.get("pairwise_analysis") or [])

    def abs_diff(p):
        c = p.get("diff_correlation")
        return abs(c) if isinstance(c, (int, float)) else 0.0

    pairs_sorted = sorted(pairs, key=abs_diff, reverse=True)[:top_pairs]

    compact_pairs = []

    for p in pairs_sorted:
        best = (p.get("cross_correlation") or {}).get("best") or {}

        compact_pairs.append({
            "series_A": p.get("series_A"),
            "series_B": p.get("series_B"),
            "overlap_n_lag0": p.get("overlap_n_lag0"),
            "overlap_year_range": p.get("overlap_year_range"),
            "best_overlap_n": best.get("overlap_n"),
            "best_lag": best.get("lag"),
            "best_corr": best.get("correlation"),
            "best_score": best.get("score"),
            "corr_lag0": p.get("pearson_corr_lag0"),
            "pearson_p_value": _format_p(p.get("pearson_p_value")),
            "trend_corr": p.get("trend_correlation"),
            "residual_corr": p.get("residual_correlation"),
            "diff_corr": p.get("diff_correlation"),
            "diff_p_value": _format_p(p.get("diff_p_value")),
            "diff_supports": p.get("diff_supports_relation"),
            "diff_strength": p.get("diff_strength"),
            "trend_driven": p.get("trend_driven"),
            "trend_strength": p.get("trend_strength"),
            "residual_strength": p.get("residual_strength"),
            "spurious_risk": p.get("spurious_risk"),
            "seasonality_overlap": p.get("seasonality_overlap"),
            "stationarity": p.get("stationarity"),
        })

    return {
        "entity": entity,
        "entity_range": ent.get("entity_range"),
        "series_ranges": ent.get("series_ranges"),
        "overlap_range": ent.get("overlap_range"),
        "normalization": meta.get("normalization"),
        "decomposition_period": meta.get("decomposition_period"),
        "entity_warnings": ent.get("warnings", []) or [],
        "series": compact_series,
        "pairwise": compact_pairs,
    }


def build_llm_prompt(
    result: dict,
    entity: str,
    specific_events: bool = False,
    top_pairs: int = 10,
    top_freqs: int = 5
) -> str:
    system = SYSTEM_SPECIFIC if specific_events else SYSTEM_GENERIC

    payload = _compact_entity_payload(
        result,
        entity,
        top_pairs=top_pairs,
        top_freqs=top_freqs,
    )

    return system + "\n\nDATA (JSON):\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )