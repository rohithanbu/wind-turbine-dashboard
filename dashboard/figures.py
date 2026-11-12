"""Pure figure builders: each takes already-filtered data and returns a styled go.Figure.

No Dash imports here - these functions are easy to test or reuse in a notebook.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .config import (
    COLORS, FONT_FAMILY, INTERVAL_HOURS, MAX_HUED_SECTORS, MAX_SCATTER_POINTS,
    MONTH_LABELS, SECTOR_COLORS, SECTOR_NAMES, SECTORS,
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


def empty_figure(message: str = "No readings match the current filters") -> go.Figure:
    """Placeholder figure shown when the filters leave nothing to plot."""
    fig = _base_layout(go.Figure(), x_title="", y_title="")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(color=COLORS["muted"], size=13))
    return fig


# --- Scatter: power curve ---------------------------------------------------

def plateau_wind_speed(df: pd.DataFrame, bin_width: float = 0.5) -> float | None:
    """Wind speed where the median power curve first reaches 95% of its peak.

    Answers "at what wind speed does the curve flatten?" from the data in view.
    """
    if len(df) < 500:
        return None
    bins = (df["wind_speed"] / bin_width).round() * bin_width
    grouped = df.groupby(bins)["active_power"]
    medians = grouped.median()[grouped.size() >= 20]  # ignore sparse bins
    if medians.empty or medians.max() <= 0:
        return None
    return float(medians[medians >= 0.95 * medians.max()].index.min())


def scatter_figure(df: pd.DataFrame, theoretical: pd.DataFrame,
                   highlight: tuple[str, ...], selection: dict | None,
                   show_plateau: bool = True) -> go.Figure:
    """Wind speed (x) vs active power (y), with the theoretical curve overlaid.

    Highlighted sectors take their categorical hue; everything else recedes to a
    neutral context colour so the power-curve shape stays visible.
    """
    if df.empty:
        return empty_figure()

    sample = df.sample(MAX_SCATTER_POINTS, random_state=0) if len(df) > MAX_SCATTER_POINTS else df
    hover = ("<b>%{customdata}</b> sector<br>Wind speed %{x:.1f} m/s"
             "<br>Active power %{y:,.0f} kW<extra></extra>")

    def points(frame: pd.DataFrame, name: str, color: str, opacity: float) -> go.Scattergl:
        return go.Scattergl(
            x=frame["wind_speed"].round(2), y=frame["active_power"].round(1),
            customdata=frame["sector"], mode="markers", name=name,
            marker=dict(size=5, color=color, opacity=opacity, line=dict(width=0)),
            hovertemplate=hover,
        )

    fig = go.Figure()
    if not highlight:
        fig.add_trace(points(sample, "Readings", COLORS["muted"], 0.35))
    else:
        is_hl = sample["sector"].isin(highlight)
        fig.add_trace(points(sample[~is_hl], "Other sectors", COLORS["context"], 0.3))
        if len(highlight) <= MAX_HUED_SECTORS:
            for sector in highlight:
                fig.add_trace(points(sample[sample["sector"] == sector],
                                     SECTOR_NAMES[sector], SECTOR_COLORS[sector], 0.75))
        else:
            # Too many hues to separate reliably on overlapping dots: one highlight colour.
            fig.add_trace(points(sample[is_hl], f"Selected sectors ({len(highlight)})",
                                 COLORS["ink"], 0.6))

    fig.add_trace(go.Scatter(
        x=theoretical["wind_speed"], y=theoretical["theoretical_power"],
        mode="lines", name="Theoretical curve",
        line=dict(color=COLORS["ink"], width=2, dash="dash"),
        hovertemplate="Theoretical %{y:,.0f} kW at %{x:.1f} m/s<extra></extra>",
    ))

    _base_layout(fig, x_title="Wind speed (m/s)", y_title="Active power (kW)")

    plateau = plateau_wind_speed(df) if show_plateau else None
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


# --- Line: monthly trend ----------------------------------------------------

def line_figure(df: pd.DataFrame, sectors: tuple[str, ...],
                months: tuple[int, int]) -> go.Figure:
    """Mean active power per month; one line per selected sector, else overall.

    The selected month range is shown as a shaded band (the brush).
    """
    if df.empty:
        return empty_figure()

    all_months = pd.RangeIndex(1, 13, name="month")
    fig = go.Figure()

    def monthly_line(series: pd.Series, name: str, color: str, dash: str = "solid") -> go.Scatter:
        y = series.reindex(all_months)
        return go.Scatter(
            x=list(all_months), y=y.round(1), name=name, mode="lines+markers",
            line=dict(color=color, width=2, dash=dash),
            marker=dict(size=8, color=color, line=dict(color=COLORS["surface"], width=2)),
            hovertemplate=f"{name}: %{{y:,.0f}} kW<extra></extra>",
        )

    by_month = df.groupby("month")
    if sectors:
        for sector in sectors:
            subset = df[df["sector"] == sector]
            fig.add_trace(monthly_line(subset.groupby("month")["active_power"].mean(),
                                       SECTOR_NAMES[sector], SECTOR_COLORS[sector]))
        theoretical = df[df["sector"].isin(sectors)].groupby("month")["theoretical_power"].mean()
    else:
        fig.add_trace(monthly_line(by_month["active_power"].mean(), "Actual", COLORS["ink"]))
        theoretical = by_month["theoretical_power"].mean()
    fig.add_trace(monthly_line(theoretical, "Theoretical", COLORS["muted"], dash="dash"))

    _base_layout(fig, x_title="Month (2018)", y_title="Mean active power (kW)")
    fig.update_xaxes(tickmode="array", tickvals=list(all_months), ticktext=MONTH_LABELS,
                     range=[0.5, 12.5], showgrid=False)
    fig.update_yaxes(fixedrange=True, rangemode="tozero")

    if tuple(months) != (1, 12):
        fig.add_vrect(x0=months[0] - 0.5, x1=months[1] + 0.5, fillcolor=COLORS["brush"],
                      line_width=0, layer="below")

    # Horizontal-only brushing matches the left-to-right reading of time.
    fig.update_layout(dragmode="select", selectdirection="h", hovermode="x unified")
    return fig


# --- Bar: wind direction sectors --------------------------------------------

def sector_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sector mean power, energy and share of time, in compass order."""
    g = df.groupby("sector")["active_power"].agg(mean_kw="mean", total_kw="sum", count="size")
    g = g.reindex(SECTORS)
    g["count"] = g["count"].fillna(0)
    g["energy_mwh"] = g["total_kw"].fillna(0) * INTERVAL_HOURS / 1000
    g["share"] = g["count"] / max(g["count"].sum(), 1)
    return g


def bar_figure(df: pd.DataFrame, selected: tuple[str, ...], metric: str) -> go.Figure:
    """One bar per compass sector, each in its fixed sector hue.

    Unselected sectors fade when a selection exists, so the selection reads at a glance.
    """
    if df.empty:
        return empty_figure()

    summary = sector_summary(df)
    if metric == "energy":
        y, y_title = summary["energy_mwh"], "Energy generated (MWh)"
    else:
        y, y_title = summary["mean_kw"].fillna(0), "Mean active power (kW)"

    opacity = [1.0 if not selected or s in selected else 0.3 for s in SECTORS]
    customdata = np.column_stack([
        [SECTOR_NAMES[s] for s in SECTORS], summary["mean_kw"].fillna(0),
        summary["energy_mwh"], summary["share"] * 100,
    ])

    fig = go.Figure(go.Bar(
        x=SECTORS, y=y.round(1), customdata=customdata,
        marker=dict(color=[SECTOR_COLORS[s] for s in SECTORS], opacity=opacity,
                    cornerradius=4, line=dict(width=0)),
        hovertemplate=("<b>%{customdata[0]}</b><br>Mean power %{customdata[1]:,.0f} kW"
                       "<br>Energy %{customdata[2]:,.0f} MWh"
                       "<br>Time from this sector %{customdata[3]:.1f}%<extra></extra>"),
    ))
    _base_layout(fig, x_title="Wind direction sector", y_title=y_title)
    fig.update_xaxes(showgrid=False, fixedrange=True, tickfont=dict(color=COLORS["ink_secondary"]))
    fig.update_yaxes(fixedrange=True, rangemode="tozero")
    fig.update_layout(bargap=0.25, showlegend=False, dragmode=False)
    return fig


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
