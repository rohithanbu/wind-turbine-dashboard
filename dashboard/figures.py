"""Pure figure builders: each takes already-filtered data and returns a styled go.Figure.

No Dash imports here - these functions are easy to test or reuse in a notebook.
Each view also has a small ``*_title`` function that turns the data in view into an
insight-driven card title, so the headline always describes what the chart shows.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .config import (
    COLORS, FONT_FAMILY, INTERVAL_HOURS, MAX_HUED_SECTORS, MAX_SCATTER_POINTS,
    MONTH_LABELS, MONTH_NAMES, RATED_POWER_KW, SECTOR_COLORS, SECTOR_NAMES, SECTOR_SYMBOLS,
    SECTORS,
)


# --- Shared styling ---------------------------------------------------------

def _base_layout(fig: go.Figure, *, x_title: str, y_title: str) -> go.Figure:
    """Apply the common look: quiet axes, hairline grid, system font."""
    axis = dict(
        showgrid=True, gridcolor=COLORS["grid"], gridwidth=1,
        linecolor=COLORS["axis"], zeroline=False, ticks="",
        tickfont=dict(color=COLORS["muted"], size=11),
        title=dict(font=dict(color=COLORS["ink_secondary"], size=12), standoff=8),
    )
    fig.update_layout(
        template="none",
        font=dict(family=FONT_FAMILY, color=COLORS["ink"], size=12),
        paper_bgcolor=COLORS["surface"],
        plot_bgcolor=COLORS["surface"],
        margin=dict(l=56, r=16, t=36, b=48),
        hoverlabel=dict(bgcolor="white", bordercolor=COLORS["grid"],
                        font=dict(family=FONT_FAMILY, color=COLORS["ink"], size=12)),
        legend=dict(orientation="h", x=0, y=1.02, xanchor="left", yanchor="bottom",
                    font=dict(color=COLORS["ink_secondary"], size=11)),
    )
    fig.update_xaxes(axis, title_text=x_title)
    fig.update_yaxes(axis, title_text=y_title)
    return fig


def empty_figure(message: str = "No readings match the current filters · use Reset all") -> go.Figure:
    """Placeholder figure shown when the filters leave nothing to plot."""
    fig = _base_layout(go.Figure(), x_title="", y_title="")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(color=COLORS["muted"], size=13))
    return fig


def selection_colors(selected: tuple[str, ...]) -> dict[str, str]:
    """Colour for each selected sector, shared by every view.

    Nothing is hued by default (one neutral colour plus a highlight). Selected sectors
    take their fixed hue, so a sector looks the same everywhere; beyond MAX_HUED_SECTORS
    the hues stop being reliably distinguishable, so the selection shares one colour.
    """
    if len(selected) <= MAX_HUED_SECTORS:
        return {s: SECTOR_COLORS[s] for s in selected}
    return {s: COLORS["ink_secondary"] for s in selected}


# --- Scatter: power curve ---------------------------------------------------

def binned_median(df: pd.DataFrame, bin_width: float = 0.5, min_count: int = 20) -> pd.Series:
    """Median active power per wind-speed bin, skipping sparse bins."""
    bins = (df["wind_speed"] / bin_width).round() * bin_width
    grouped = df.groupby(bins)["active_power"]
    return grouped.median()[grouped.size() >= min_count]


def plateau_wind_speed(df: pd.DataFrame, bin_width: float = 0.5) -> float | None:
    """Wind speed where the median power curve first reaches 95% of its peak.

    Answers "at what wind speed does the curve flatten?" from the data in view.
    """
    if len(df) < 500:
        return None
    medians = binned_median(df, bin_width)
    if medians.empty or medians.max() <= 0:
        return None
    return float(medians[medians >= 0.95 * medians.max()].index.min())


def scatter_figure(df: pd.DataFrame, theoretical: pd.DataFrame,
                   highlight: tuple[str, ...], selection: dict | None,
                   plateau: float | None = None, show_median: bool = True) -> go.Figure:
    """Wind speed (x) vs active power (y), with the theoretical curve overlaid.

    The points are small and translucent so dense regions read darker; a binned median
    line and the plateau marker summarise the actual curve. Highlighted sectors take their
    selection colour; everything else recedes to a neutral context colour.

    Points are drawn as one trace per sector: the sector name then lives in each trace's
    hover template instead of being repeated for every point, and coordinates are sent as
    float32. Together that keeps the update payload small enough to feel instant.
    """
    if df.empty:
        return empty_figure()

    sample = df.sample(MAX_SCATTER_POINTS, random_state=0) if len(df) > MAX_SCATTER_POINTS else df
    by_sector = {s: frame for s, frame in sample.groupby("sector")}
    # Style the empty figure first: Plotly's axis updates get slow once large traces exist.
    fig = _base_layout(go.Figure(), x_title="Wind speed (m/s)", y_title="Active power (kW)")
    # Fixed domains so the axes don't jump when other views change the filters.
    fig.update_xaxes(range=[0, 26])
    fig.update_yaxes(range=[-150, RATED_POWER_KW + 250])
    legend_shown: set[str] = set()

    def add_points(sector: str, color: str, opacity: float, legend_name: str, group: str) -> None:
        frame = by_sector.get(sector)
        if frame is None or frame.empty:
            return
        fig.add_trace(go.Scattergl(
            x=frame["wind_speed"].to_numpy(np.float32), y=frame["active_power"].to_numpy(np.float32),
            mode="markers", name=legend_name, legendgroup=group, showlegend=group not in legend_shown,
            marker=dict(size=4, color=color, opacity=opacity, line=dict(width=0)),
            hovertemplate=(f"<b>{SECTOR_NAMES[sector]}</b> sector<br>Wind speed %{{x:.1f}} m/s"
                           "<br>Active power %{y:,.0f} kW<extra></extra>"),
        ))
        legend_shown.add(group)

    if not highlight:
        for sector in SECTORS:
            add_points(sector, COLORS["muted"], 0.2, "Readings", "readings")
        median_source, median_name = df, "Median actual"
    else:
        for sector in SECTORS:
            if sector not in highlight:
                add_points(sector, COLORS["context"], 0.2, "Other sectors", "other")
        colors = selection_colors(highlight)
        for sector in highlight:
            if len(highlight) <= MAX_HUED_SECTORS:
                add_points(sector, colors[sector], 0.55, SECTOR_NAMES[sector], sector)
            else:
                add_points(sector, colors[sector], 0.3, f"Selected sectors ({len(highlight)})", "selected")
        median_source, median_name = df[df["sector"].isin(highlight)], "Median actual (selected)"

    fig.add_trace(go.Scatter(
        x=theoretical["wind_speed"], y=theoretical["theoretical_power"],
        mode="lines", name="Theoretical curve",
        line=dict(color=COLORS["ink_secondary"], width=2, dash="dash"),
        hovertemplate="Theoretical %{y:,.0f} kW at %{x:.1f} m/s<extra></extra>",
    ))
    medians = binned_median(median_source) if show_median else pd.Series(dtype=float)
    if not medians.empty:
        # A light halo keeps the median line readable on top of dense points.
        fig.add_trace(go.Scatter(
            x=medians.index, y=medians.round(0), mode="lines", showlegend=False, hoverinfo="skip",
            line=dict(color=COLORS["surface"], width=6),
        ))
        fig.add_trace(go.Scatter(
            x=medians.index, y=medians.round(0), mode="lines", name=median_name,
            line=dict(color=COLORS["ink"], width=2.5),
            hovertemplate="Median actual %{y:,.0f} kW at %{x:.1f} m/s<extra></extra>",
        ))

    if plateau is not None:
        fig.add_vline(x=plateau, line=dict(color=COLORS["muted"], width=1, dash="dot"),
                      annotation=dict(text=f"Plateau ≈ {plateau:g} m/s", font_size=11,
                                      font_color=COLORS["ink_secondary"]),
                      annotation_position="top left")

    # Re-draw an active brush so it survives re-renders triggered by other views.
    if selection and selection.get("x") and selection.get("y"):
        (x0, x1), (y0, y1) = selection["x"], selection["y"]
        fig.update_layout(selections=[dict(type="rect", xref="x", yref="y",
                                           x0=x0, x1=x1, y0=y0, y1=y1)])

    fig.update_layout(dragmode="select", uirevision="scatter")
    if len(df) > len(sample):
        fig.add_annotation(text=f"Showing a {len(sample):,}-point sample of {len(df):,}",
                           xref="paper", yref="paper", x=1, y=0, xanchor="right", yanchor="bottom",
                           showarrow=False, font=dict(size=10, color=COLORS["muted"]))
    return fig


def power_curve_title(plateau: float | None, perf_mode: str) -> str:
    """Headline for the power curve card."""
    if plateau is not None:
        return f"Output levels off at about {plateau:g} m/s"
    if perf_mode == "under":
        return "Underperforming readings fall well below the manufacturer curve"
    return "Power curve: actual vs. manufacturer"


# --- Line: monthly trend ----------------------------------------------------

def line_figure(df: pd.DataFrame, sectors: tuple[str, ...],
                months: tuple[int, int]) -> go.Figure:
    """Mean active power per month; one line per selected sector, else overall.

    The y-axis is fixed at 0 to rated power so lines stay comparable across selections.
    Each sector line also has its own marker shape, so lines stay distinguishable without
    colour (greyscale, colour-vision deficiency). Months with no matching readings are
    marked with an × on the baseline instead of leaving an unexplained gap. The selected
    month range is shown as a shaded band.
    """
    if df.empty:
        return empty_figure()

    all_months = pd.RangeIndex(1, 13, name="month")
    # Style the empty figure first (cheaper than restyling after the traces exist).
    fig = _base_layout(go.Figure(), x_title="Month (2018)", y_title="Mean active power (kW)")
    fig.update_xaxes(tickmode="array", tickvals=list(all_months), ticktext=MONTH_LABELS,
                     range=[0.5, 12.5], showgrid=False)
    # Fixed 0-to-rated-power domain (a little below 0 so the × markers aren't clipped).
    fig.update_yaxes(fixedrange=True, range=[-150, RATED_POWER_KW])

    # (monthly means, name, colour, dash, marker symbol) for each line, in drawing order.
    series: list[tuple[pd.Series, str, str, str, str]] = []
    if sectors:
        theoretical = df[df["sector"].isin(sectors)].groupby("month")["theoretical_power"].mean()
        if len(sectors) <= MAX_HUED_SECTORS:
            colors = selection_colors(sectors)
            for sector in sectors:
                subset = df[df["sector"] == sector]
                series.append((subset.groupby("month")["active_power"].mean(), SECTOR_NAMES[sector],
                               colors[sector], "solid", SECTOR_SYMBOLS[sector]))
        else:
            # Too many lines to tell apart: show the selection as one combined line.
            selected = df[df["sector"].isin(sectors)]
            series.append((selected.groupby("month")["active_power"].mean(),
                           f"Selected sectors ({len(sectors)})", selection_colors(sectors)[sectors[0]],
                           "solid", "circle"))
    else:
        by_month = df.groupby("month")
        series.append((by_month["active_power"].mean(), "Actual", COLORS["ink"], "solid", "circle"))
        theoretical = by_month["theoretical_power"].mean()
    series.append((theoretical, "Theoretical", COLORS["muted"], "dash", "circle"))

    # Lines first, then one × layer per line (empty when no month is missing).
    monthly = [(s.reindex(all_months), name, color, dash, symbol) for s, name, color, dash, symbol in series]
    for y, name, color, dash, symbol in monthly:
        fig.add_trace(go.Scatter(
            x=list(all_months), y=y.round(1), name=name, mode="lines+markers",
            line=dict(color=color, width=2, dash=dash),
            marker=dict(size=9, symbol=symbol, color=color, line=dict(color=COLORS["surface"], width=1.5)),
            hovertemplate=f"{name}: %{{y:,.0f}} kW<extra></extra>",
        ))
    any_missing = False
    for y, name, color, _dash, _symbol in monthly:
        missing = [m for m in all_months if pd.isna(y[m])]
        any_missing = any_missing or bool(missing)
        fig.add_trace(go.Scatter(
            x=missing, y=[0] * len(missing), mode="markers", showlegend=False,
            marker=dict(symbol="x-thin", size=10, color=color, line=dict(color=color, width=2)),
            hovertemplate=f"{name}: no matching readings<extra></extra>",
        ))

    fig.add_annotation(text="× = no matching readings that month" if any_missing else "",
                       showarrow=False, xref="paper", yref="paper", x=1, y=1.02,
                       xanchor="right", yanchor="bottom", font=dict(size=11, color=COLORS["muted"]))
    fig.add_vrect(x0=months[0] - 0.5, x1=months[1] + 0.5, fillcolor=COLORS["brush"],
                  line_width=0, layer="below", visible=tuple(months) != (1, 12))

    # Horizontal-only brushing matches the left-to-right reading of time.
    fig.update_layout(dragmode="select", selectdirection="h", hovermode="x unified")
    return fig


def line_title(df: pd.DataFrame, sectors: tuple[str, ...]) -> str:
    """Headline for the monthly card: the month with the largest shortfall vs. theoretical."""
    subset = df[df["sector"].isin(sectors)] if sectors else df
    if subset.empty:
        return "Monthly trend"
    by_month = subset.groupby("month")[["active_power", "theoretical_power"]].mean()
    gap = (by_month["theoretical_power"] - by_month["active_power"]).dropna()
    if gap.empty:
        return "Monthly trend"
    if gap.max() <= 0:
        return "Actual output keeps up with the manufacturer curve every month"
    month = int(gap.idxmax())
    return f"Biggest shortfall vs. theoretical: {MONTH_NAMES[month - 1]} ({gap.max():,.0f} kW below)"


# --- Wind rose: output by direction sector ----------------------------------

def sector_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sector mean power, energy and share of time, in compass order."""
    g = df.groupby("sector")["active_power"].agg(mean_kw="mean", total_kw="sum", count="size")
    g = g.reindex(SECTORS)
    g["count"] = g["count"].fillna(0)
    g["energy_mwh"] = g["total_kw"].fillna(0) * INTERVAL_HOURS / 1000
    g["share"] = g["count"] / max(g["count"].sum(), 1)
    return g


def _nice_ticks(vmax: float, target: int = 3) -> list[float]:
    """Round tick values (1, 2, 2.5, 5 x 10^k steps) up to vmax."""
    if vmax <= 0:
        return []
    base = 10 ** math.floor(math.log10(vmax / target))
    step = next(base * m for m in (1, 2, 2.5, 5, 10) if vmax / (base * m) <= target)
    return [step * i for i in range(1, int(vmax // step) + 1)]


def rose_figure(summary: pd.DataFrame, selected: tuple[str, ...], metric: str) -> go.Figure:
    """Wind rose: one wedge per compass sector, N at the top, clockwise.

    Direction is circular, so angle encodes the sector. The value sets the wedge radius
    on a square-root scale, so wedge *area* is proportional to the value: by Stevens' law
    people judge these wedges by area, and a linear radius would square the differences.
    All wedges share one neutral colour; selected sectors take their selection colour plus
    a dark outline, so the selection still reads in greyscale.
    """
    if summary["count"].sum() == 0:
        return empty_figure()

    if metric == "energy":
        values, label = summary["energy_mwh"], "Energy generated (MWh)"
    else:
        values, label = summary["mean_kw"].fillna(0), "Mean active power (kW)"
    values = values.clip(lower=0)
    vmax = float(values.max())
    ticks = _nice_ticks(vmax)

    colors = selection_colors(selected)
    if selected:
        wedge_colors = [colors.get(s, COLORS["context"]) for s in SECTORS]
    else:
        wedge_colors = [COLORS["muted"]] * len(SECTORS)
    outline_colors = [COLORS["ink"] if s in selected else COLORS["surface"] for s in SECTORS]
    outline_widths = [2 if s in selected else 1.5 for s in SECTORS]
    customdata = list(zip(
        SECTORS, [SECTOR_NAMES[s] for s in SECTORS], summary["mean_kw"].fillna(0),
        summary["energy_mwh"], summary["share"] * 100,
    ))

    fig = go.Figure(go.Barpolar(
        r=np.sqrt(values).round(3), theta=SECTORS, customdata=customdata,
        marker=dict(color=wedge_colors, line=dict(color=outline_colors, width=outline_widths)),
        hovertemplate=("<b>%{customdata[1]}</b><br>Mean power %{customdata[2]:,.0f} kW"
                       "<br>Energy %{customdata[3]:,.0f} MWh"
                       "<br>Time from this sector %{customdata[4]:.1f}%<extra></extra>"),
    ))
    fig.update_layout(
        template="none",
        font=dict(family=FONT_FAMILY, color=COLORS["ink"], size=12),
        paper_bgcolor=COLORS["surface"],
        margin=dict(l=40, r=40, t=24, b=56),
        hoverlabel=dict(bgcolor="white", bordercolor=COLORS["grid"],
                        font=dict(family=FONT_FAMILY, color=COLORS["ink"], size=12)),
        # Polar charts only report clicks when a drag mode is on (double-click resets a zoom).
        showlegend=False, dragmode="zoom",
        polar=dict(
            bgcolor=COLORS["surface"], bargap=0.06,
            angularaxis=dict(direction="clockwise", rotation=90, type="category",
                             linecolor=COLORS["axis"], gridcolor=COLORS["grid"],
                             tickfont=dict(color=COLORS["ink_secondary"], size=12)),
            # Ticks sit at sqrt(value) but are labelled with the value itself.
            radialaxis=dict(range=[0, math.sqrt(vmax) * 1.05 if vmax else 1],
                            tickvals=[math.sqrt(t) for t in ticks],
                            ticktext=[f"{t:,.0f}" for t in ticks],
                            angle=67.5, tickangle=67.5, linecolor=COLORS["axis"],
                            gridcolor=COLORS["grid"], showline=False,
                            tickfont=dict(color=COLORS["muted"], size=10)),
        ),
        annotations=[dict(text=f"{label} · wedge area is proportional to the value", showarrow=False,
                          xref="paper", yref="paper", x=0.5, y=-0.06, xanchor="center", yanchor="top",
                          font=dict(size=11, color=COLORS["ink_secondary"]))],
    )
    return fig


def rose_title(summary: pd.DataFrame, metric: str) -> str:
    """Headline for the wind rose card: the leading direction for the chosen metric.

    An average from a handful of readings isn't a finding, so only sectors with a
    reasonable share of the readings in view can headline the mean.
    """
    column = "energy_mwh" if metric == "energy" else "mean_kw"
    min_count = 1 if metric == "energy" else max(20, 0.02 * summary["count"].sum())
    values = summary.loc[summary["count"] >= min_count, column].dropna()
    if values.empty:
        return "Output by wind direction"
    top = SECTOR_NAMES[values.idxmax()]
    if metric == "energy":
        return f"{top} winds produce the most energy"
    return f"{top} winds give the strongest average output"


# --- KPI summary ------------------------------------------------------------

def compute_kpis(df: pd.DataFrame) -> dict[str, str]:
    """Headline numbers for the KPI row, already formatted for display."""
    if df.empty:
        return dict(energy="–", max_wind="–", active="–", efficiency="–")
    produced = df["active_power"].clip(lower=0)
    theoretical_total = df["theoretical_power"].sum()
    return dict(
        energy=f"{produced.sum() * INTERVAL_HOURS / 1000:,.0f} MWh",
        max_wind=f"{df['wind_speed'].max():.1f} m/s",
        active=f"{(df['active_power'] > 0).mean():.0%}",
        efficiency=f"{produced.sum() / theoretical_total:.0%}" if theoretical_total else "–",
    )
