"""Pure figure builders: each takes already-filtered data and returns a styled go.Figure.

No Dash imports here - these functions are easy to test or reuse in a notebook.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .config import (
    COLORS, FONT_FAMILY, INTERVAL_HOURS, MAX_HUED_SECTORS, MAX_SCATTER_POINTS,
    MONTH_LABELS, RATED_POWER_KW, SECTOR_COLORS, SECTOR_NAMES, SECTORS,
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
    the hues stop being reliably distinguishable, so the selection shares one ink colour.
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
                   show_summary: bool = True) -> go.Figure:
    """Wind speed (x) vs active power (y), with the theoretical curve overlaid.

    The points are small and translucent so dense regions read darker; a binned median
    line and the plateau marker summarise the actual curve (``show_summary``). Highlighted
    sectors take their selection colour; everything else recedes to a neutral context colour.
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
            marker=dict(size=4, color=color, opacity=opacity, line=dict(width=0)),
            hovertemplate=hover,
        )

    fig = go.Figure()
    if not highlight:
        fig.add_trace(points(sample, "Readings", COLORS["muted"], 0.2))
        median_source, median_name = df, "Median actual"
    else:
        is_hl = sample["sector"].isin(highlight)
        fig.add_trace(points(sample[~is_hl], "Other sectors", COLORS["context"], 0.2))
        colors = selection_colors(highlight)
        if len(highlight) <= MAX_HUED_SECTORS:
            for sector in highlight:
                fig.add_trace(points(sample[sample["sector"] == sector],
                                     SECTOR_NAMES[sector], colors[sector], 0.55))
        else:
            fig.add_trace(points(sample[is_hl], f"Selected sectors ({len(highlight)})",
                                 colors[highlight[0]], 0.3))
        median_source, median_name = df[df["sector"].isin(highlight)], "Median actual (selected)"

    fig.add_trace(go.Scatter(
        x=theoretical["wind_speed"], y=theoretical["theoretical_power"],
        mode="lines", name="Theoretical curve",
        line=dict(color=COLORS["ink_secondary"], width=2, dash="dash"),
        hovertemplate="Theoretical %{y:,.0f} kW at %{x:.1f} m/s<extra></extra>",
    ))
    medians = binned_median(median_source) if show_summary else pd.Series(dtype=float)
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

    _base_layout(fig, x_title="Wind speed (m/s)", y_title="Active power (kW)")
    # Fixed domains so the axes don't jump when other views change the filters.
    fig.update_xaxes(range=[0, 26])
    fig.update_yaxes(range=[-150, RATED_POWER_KW + 250])

    plateau = plateau_wind_speed(df) if show_summary else None
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

    The y-axis is fixed at 0 to rated power so lines stay comparable across selections.
    Months with no matching readings are marked with an × on the baseline instead of
    leaving an unexplained gap. The selected month range is shown as a shaded band.
    """
    if df.empty:
        return empty_figure()

    all_months = pd.RangeIndex(1, 13, name="month")
    fig = go.Figure()
    any_missing = False

    def monthly_line(series: pd.Series, name: str, color: str, dash: str = "solid") -> None:
        nonlocal any_missing
        y = series.reindex(all_months)
        fig.add_trace(go.Scatter(
            x=list(all_months), y=y.round(1), name=name, mode="lines+markers",
            line=dict(color=color, width=2, dash=dash),
            marker=dict(size=8, color=color, line=dict(color=COLORS["surface"], width=2)),
            hovertemplate=f"{name}: %{{y:,.0f}} kW<extra></extra>",
        ))
        missing = [m for m in all_months if pd.isna(y[m])]
        if missing:
            any_missing = True
            fig.add_trace(go.Scatter(
                x=missing, y=[0] * len(missing), mode="markers", showlegend=False,
                marker=dict(symbol="x-thin", size=10, color=color, line=dict(color=color, width=2)),
                hovertemplate=f"{name}: no matching readings<extra></extra>",
            ))

    if sectors:
        theoretical = df[df["sector"].isin(sectors)].groupby("month")["theoretical_power"].mean()
        if len(sectors) <= MAX_HUED_SECTORS:
            colors = selection_colors(sectors)
            for sector in sectors:
                subset = df[df["sector"] == sector]
                monthly_line(subset.groupby("month")["active_power"].mean(),
                             SECTOR_NAMES[sector], colors[sector])
        else:
            # Too many lines to tell apart: show the selection as one combined line.
            selected = df[df["sector"].isin(sectors)]
            monthly_line(selected.groupby("month")["active_power"].mean(),
                         f"Selected sectors ({len(sectors)})", selection_colors(sectors)[sectors[0]])
    else:
        by_month = df.groupby("month")
        monthly_line(by_month["active_power"].mean(), "Actual", COLORS["ink"])
        theoretical = by_month["theoretical_power"].mean()
    monthly_line(theoretical, "Theoretical", COLORS["muted"], dash="dash")

    _base_layout(fig, x_title="Month (2018)", y_title="Mean active power (kW)")
    fig.update_xaxes(tickmode="array", tickvals=list(all_months), ticktext=MONTH_LABELS,
                     range=[0.5, 12.5], showgrid=False)
    # Fixed 0-to-rated-power domain (a little below 0 so the × markers aren't clipped).
    fig.update_yaxes(fixedrange=True, range=[-150, RATED_POWER_KW])

    if any_missing:
        fig.add_annotation(text="× = no matching readings that month", showarrow=False,
                           xref="paper", yref="paper", x=1, y=1.02, xanchor="right", yanchor="bottom",
                           font=dict(size=11, color=COLORS["muted"]))

    if tuple(months) != (1, 12):
        fig.add_vrect(x0=months[0] - 0.5, x1=months[1] + 0.5, fillcolor=COLORS["brush"],
                      line_width=0, layer="below")

    # Horizontal-only brushing matches the left-to-right reading of time.
    fig.update_layout(dragmode="select", selectdirection="h", hovermode="x unified")
    return fig


# --- Wind rose: output by direction sector ----------------------------------

def sector_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sector mean power, energy and share of time, in compass order."""
    g = df.groupby("sector")["active_power"].agg(mean_kw="mean", total_kw="sum", count="size")
    g = g.reindex(SECTORS)
    g["count"] = g["count"].fillna(0)
    g["energy_mwh"] = g["total_kw"].fillna(0) * INTERVAL_HOURS / 1000
    g["share"] = g["count"] / max(g["count"].sum(), 1)
    return g


def rose_figure(df: pd.DataFrame, selected: tuple[str, ...], metric: str) -> go.Figure:
    """Wind rose: one wedge per compass sector, N at the top, clockwise.

    Direction is circular, so angle encodes the sector and radius the output. All wedges
    share one neutral colour; selected sectors take their selection colour and the rest fade.
    """
    if df.empty:
        return empty_figure()

    summary = sector_summary(df)
    if metric == "energy":
        r, r_label = summary["energy_mwh"], "Radius: energy generated (MWh)"
    else:
        r, r_label = summary["mean_kw"].fillna(0), "Radius: mean active power (kW)"

    colors = selection_colors(selected)
    if selected:
        wedge_colors = [colors.get(s, COLORS["context"]) for s in SECTORS]
    else:
        wedge_colors = [COLORS["muted"]] * len(SECTORS)
    customdata = list(zip(
        SECTORS, [SECTOR_NAMES[s] for s in SECTORS], summary["mean_kw"].fillna(0),
        summary["energy_mwh"], summary["share"] * 100,
    ))

    fig = go.Figure(go.Barpolar(
        r=r.round(1), theta=SECTORS, customdata=customdata,
        marker=dict(color=wedge_colors, line=dict(color=COLORS["surface"], width=1.5)),
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
            radialaxis=dict(angle=67.5, tickangle=67.5, linecolor=COLORS["axis"],
                            gridcolor=COLORS["grid"], showline=False,
                            tickfont=dict(color=COLORS["muted"], size=10), nticks=4),
        ),
        annotations=[dict(text=r_label, showarrow=False, xref="paper", yref="paper",
                          x=0.5, y=-0.06, xanchor="center", yanchor="top",
                          font=dict(size=11, color=COLORS["ink_secondary"]))],
    )
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
