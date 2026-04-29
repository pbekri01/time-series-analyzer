from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional, Literal

try:
    from statsmodels.tsa.stattools import adfuller
except Exception:  # pragma: no cover
    adfuller = None


TransformKind = Literal["none", "diff", "log", "log_diff"]


@dataclass
class StationarityResult:
    original_p_value: Optional[float]
    final_p_value: Optional[float]
    is_stationary_original: Optional[bool]
    is_stationary_final: Optional[bool]
    diffs_applied: int
    transform_applied: TransformKind
    series_transformed: np.ndarray
    success: bool
    reason: str


class StationarityAnalyzer:
    """
    ADF-based stationarity checker with optional auto-differencing.
    """

    def __init__(
        self,
        alpha: float = 0.05,
        max_diffs: int = 2,
        regression: str = "c",
        autolag: str = "AIC",
        min_length: int = 8,
    ) -> None:
        self.alpha = alpha
        self.max_diffs = max_diffs
        self.regression = regression
        self.autolag = autolag
        self.min_length = min_length

    def analyze(
        self,
        y: np.ndarray,
        use_log: bool = False,
    ) -> StationarityResult:
        y = self._clean_series(y)

        if y.size < self.min_length:
            return StationarityResult(
                original_p_value=None,
                final_p_value=None,
                is_stationary_original=None,
                is_stationary_final=None,
                diffs_applied=0,
                transform_applied="none",
                series_transformed=y,
                success=False,
                reason=f"Series too short for reliable ADF test (n={y.size}).",
            )

        if adfuller is None:
            return StationarityResult(
                original_p_value=None,
                final_p_value=None,
                is_stationary_original=None,
                is_stationary_final=None,
                diffs_applied=0,
                transform_applied="none",
                series_transformed=y,
                success=False,
                reason="statsmodels is not available; ADF test could not run.",
            )

        current = y.copy()
        transform_applied: TransformKind = "none"

        if use_log:
            if np.any(current <= 0):
                return StationarityResult(
                    original_p_value=None,
                    final_p_value=None,
                    is_stationary_original=None,
                    is_stationary_final=None,
                    diffs_applied=0,
                    transform_applied="none",
                    series_transformed=y,
                    success=False,
                    reason="Log transform requested but series contains non-positive values.",
                )
            current = np.log(current)
            transform_applied = "log"

        original_p = self._safe_adf_pvalue(current)
        is_stationary_original = None if original_p is None else bool(original_p < self.alpha)

        if is_stationary_original is True:
            return StationarityResult(
                original_p_value=original_p,
                final_p_value=original_p,
                is_stationary_original=True,
                is_stationary_final=True,
                diffs_applied=0,
                transform_applied=transform_applied,
                series_transformed=current,
                success=True,
                reason="Series is already stationary under ADF.",
            )

        diffs_applied = 0
        final_p = original_p

        while diffs_applied < self.max_diffs:
            if current.size < 2:
                break

            current = np.diff(current)
            diffs_applied += 1

            if transform_applied == "log":
                transform_applied = "log_diff"
            else:
                transform_applied = "diff"

            if current.size < self.min_length:
                final_p = None
                break

            final_p = self._safe_adf_pvalue(current)
            if final_p is not None and final_p < self.alpha:
                return StationarityResult(
                    original_p_value=original_p,
                    final_p_value=final_p,
                    is_stationary_original=is_stationary_original,
                    is_stationary_final=True,
                    diffs_applied=diffs_applied,
                    transform_applied=transform_applied,
                    series_transformed=current,
                    success=True,
                    reason="Series became stationary after transformation.",
                )

        is_stationary_final = None if final_p is None else bool(final_p < self.alpha)

        return StationarityResult(
            original_p_value=original_p,
            final_p_value=final_p,
            is_stationary_original=is_stationary_original,
            is_stationary_final=is_stationary_final,
            diffs_applied=diffs_applied,
            transform_applied=transform_applied,
            series_transformed=current,
            success=bool(is_stationary_final),
            reason=(
                "Failed to confirm stationarity within max_diffs."
                if current.size >= self.min_length
                else "Series became too short after differencing."
            ),
        )

    def _safe_adf_pvalue(self, y: np.ndarray) -> Optional[float]:
        y = self._clean_series(y)

        if y.size < self.min_length:
            return None

        if np.allclose(y, y[0]):
            return None

        try:
            result = adfuller(
                y,
                regression=self.regression,
                autolag=self.autolag,
            )
            return float(result[1])
        except Exception:
            return None

    @staticmethod
    def _clean_series(y: np.ndarray) -> np.ndarray:
        arr = np.asarray(y, dtype=float).reshape(-1)
        mask = np.isfinite(arr)
        return arr[mask]