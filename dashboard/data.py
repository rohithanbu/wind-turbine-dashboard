"""Data loading, feature derivation and the shared cross-filter model."""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
import pandas as pd

from .config import (
    COLUMNS, DATA_FILE, DEFAULT_PERF_THRESHOLD, MIN_THEORETICAL_KW, SECTORS,
)


@lru_cache(maxsize=1)
def load_data() -> pd.DataFrame:
    """Read T1.csv once and add the derived columns every view relies on."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"{DATA_FILE} not found - run `python scripts/download_data.py` first."
        )

    df = pd.read_csv(DATA_FILE, encoding="latin-1")
    df.columns = COLUMNS
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d %m %Y %H:%M")
    df["month"] = df["timestamp"].dt.month

    # Bin direction into 8 compass sectors; +22.5° shifts N to straddle 0°.
    sector_idx = ((df["wind_direction"] + 22.5) % 360 // 45).astype(int)
    df["sector"] = np.asarray(SECTORS)[sector_idx.to_numpy()]

    # Actual / theoretical, only where the theoretical curve expects real output.
    theoretical = df["theoretical_power"]
    df["perf_ratio"] = np.where(
        theoretical >= MIN_THEORETICAL_KW, df["active_power"] / theoretical, np.nan
    )
    return df


@lru_cache(maxsize=1)
def theoretical_curve(bin_width: float = 0.5) -> pd.DataFrame:
    """Manufacturer power curve, reduced to one point per wind-speed bin."""
    df = load_data()
    bins = (df["wind_speed"] / bin_width).round() * bin_width
    return (
        df.groupby(bins)["theoretical_power"].mean()
        .rename_axis("wind_speed").reset_index()
    )


@dataclass(frozen=True)
class Filters:
    """The complete cross-filter state.

    Each view renders with the filters of the *other* views applied (see
    ``without``), so its own selection is shown as a highlight rather than
    collapsing the chart to just the selected marks.
    """

    sectors: tuple[str, ...] = ()
    months: tuple[int, int] = (1, 12)
    wind_range: tuple[float, float] | None = None
    power_range: tuple[float, float] | None = None
    perf_mode: str = "all"  # "all" | "under" | "normal"
    threshold: float = DEFAULT_PERF_THRESHOLD

    @classmethod
    def from_inputs(cls, sectors, months, scatter_range, perf_mode, threshold_pct) -> "Filters":
        """Build from raw Dash component values (lists, dicts, None; threshold in %)."""
        scatter_range = scatter_range or {}
        wind, power = scatter_range.get("x"), scatter_range.get("y")
        return cls(
            sectors=tuple(sectors or ()),
            months=tuple(months or (1, 12)),
            wind_range=tuple(sorted(wind)) if wind else None,
            power_range=tuple(sorted(power)) if power else None,
            perf_mode=perf_mode or "all",
            threshold=threshold_pct / 100 if threshold_pct is not None else DEFAULT_PERF_THRESHOLD,
        )

    def without(self, view: str) -> "Filters":
        """Drop the filter that a given view owns: 'sector', 'month' or 'scatter'."""
        if view == "sector":
            return replace(self, sectors=())
        if view == "month":
            return replace(self, months=(1, 12))
        if view == "scatter":
            return replace(self, wind_range=None, power_range=None)
        raise ValueError(f"Unknown view: {view}")

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return the rows matching every active filter (one boolean mask, one copy)."""
        mask = np.ones(len(df), dtype=bool)
        if self.sectors:
            mask &= df["sector"].isin(self.sectors).to_numpy()
        if self.months != (1, 12):
            mask &= df["month"].between(*self.months).to_numpy()
        if self.wind_range:
            mask &= df["wind_speed"].between(*self.wind_range).to_numpy()
        if self.power_range:
            mask &= df["active_power"].between(*self.power_range).to_numpy()
        if self.perf_mode != "all":
            # NaN ratios (below cut-in) compare False, so they count as "normal".
            under = (df["perf_ratio"] < self.threshold).to_numpy()
            mask &= under if self.perf_mode == "under" else ~under
        return df[mask]
