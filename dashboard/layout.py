"""Static component tree. All behaviour lives in callbacks.py; all styling in assets/style.css."""
from __future__ import annotations

import pandas as pd
from dash import dcc, html

from .config import (
    DEFAULT_PERF_THRESHOLD, MONTH_LABELS, SECTOR_COLORS, SECTOR_NAMES, SECTORS,
)

# Shared Plotly config: no logo, only the tools each view actually needs.
GRAPH_CONFIG = {"displaylogo": False, "responsive": True}


def _kpi(kpi_id: str, label: str, hint: str) -> html.Div:
    return html.Div(className="kpi", children=[
        html.Span(label, className="kpi-label"),
        html.Span("–", id=kpi_id, className="kpi-value"),
        html.Span(hint, className="kpi-hint"),
    ])


def _card(title: str, subtitle: str, graph: dcc.Graph, *, controls=None,
          class_name: str = "", tall: bool = False) -> html.Section:
    # A responsive dcc.Graph fills 100% of its parent, so the sized box is the wrapper.
    return html.Section(className=f"card {class_name}".strip(), children=[
        html.Div(className="card-header", children=[
            html.Div([html.H2(title), html.P(subtitle, className="card-subtitle")]),
            controls,
        ]),
        html.Div(graph, className="graph-box graph-box-tall" if tall else "graph-box"),
    ])


def _filter_group(title: str, *children) -> html.Div:
    return html.Div(className="filter-group", children=[html.H3(title), *children])


def _sidebar() -> html.Aside:
    sector_options = [
        {"label": html.Span(className="sector-option", children=[
            html.Span(className="swatch", style={"backgroundColor": SECTOR_COLORS[s]}),
            html.Span(f"{s}", className="sector-code"),
            html.Span(SECTOR_NAMES[s], className="sector-name"),
        ]), "value": s}
        for s in SECTORS
    ]
    return html.Aside(className="sidebar", children=[
        html.Div(className="sidebar-header", children=[
            html.H2("Filters"),
            html.Button("Reset all", id="reset-button", className="reset-button", n_clicks=0),
        ]),
        _filter_group(
            "Wind direction",
            dcc.Checklist(id="sector-filter", options=sector_options, value=[],
                          className="sector-checklist"),
            html.P("None checked = all sectors. Clicking a bar toggles it too.", className="help"),
        ),
        _filter_group(
            "Months",
            dcc.RangeSlider(id="month-filter", min=1, max=12, step=1, value=[1, 12],
                            marks={i + 1: m[0] for i, m in enumerate(MONTH_LABELS)},
                            allowCross=False, allow_direct_input=False),
            html.P("Or drag across the monthly trend chart.", className="help"),
        ),
        _filter_group(
            "Performance",
            dcc.RadioItems(id="perf-mode", value="all", className="perf-mode", options=[
                {"label": "All readings", "value": "all"},
                {"label": "Underperforming only", "value": "under"},
                {"label": "Normal only", "value": "normal"},
            ]),
            html.Label("Underperforming below % of theoretical", className="help",
                       htmlFor="perf-threshold"),
            # Value is a whole percentage; Filters converts it to a ratio.
            dcc.Slider(id="perf-threshold", min=50, max=95, step=5,
                       value=round(DEFAULT_PERF_THRESHOLD * 100), disabled=True,
                       marks={v: f"{v}%" for v in (50, 70, 95)},
                       tooltip={"placement": "bottom", "template": "{value}%"},
                       allow_direct_input=False),
        ),
        html.Div(className="filter-group how-to", children=[
            html.H3("How to explore"),
            html.Ul([
                html.Li("Drag a box on the power curve to brush a wind-speed / power range."),
                html.Li("Click a bar to highlight a direction sector in every view."),
                html.Li("Drag across months, or click one, to focus a period."),
                html.Li("Double-click a chart to clear its brush."),
            ]),
        ]),
    ])


def build_layout(df: pd.DataFrame) -> html.Div:
    """Assemble the full page. ``df`` is only used for header context."""
    start, end = df["timestamp"].min(), df["timestamp"].max()
    return html.Div(className="app", children=[
        # Selection state that isn't owned by a visible control.
        dcc.Store(id="scatter-range", data=None),

        html.Header(className="app-header", children=[
            html.Div([
                html.H1("Wind Turbine Performance"),
                html.P(f"SCADA readings every 10 minutes · {start:%d %b %Y} – {end:%d %b %Y}",
                       className="subtitle"),
            ]),
            html.P(id="reading-count", className="reading-count"),
        ]),

        html.Div(className="app-body", children=[
            _sidebar(),
            html.Main(className="main", children=[
                html.Section(className="kpi-row", children=[
                    _kpi("kpi-energy", "Energy generated", "Sum of active power over time"),
                    _kpi("kpi-max-wind", "Max wind speed", "Highest 10-min reading"),
                    _kpi("kpi-active", "Active time", "Readings with power > 0 kW"),
                    _kpi("kpi-efficiency", "Actual / theoretical", "Energy vs. manufacturer curve"),
                ]),
                html.Div(className="chart-grid", children=[
                    _card("Power curve", "Active power vs. wind speed · drag a box to brush",
                          dcc.Graph(id="scatter-chart",
                                    config={**GRAPH_CONFIG,
                                            "modeBarButtonsToRemove": ["lasso2d", "autoScale2d"]}),
                          class_name="card-scatter", tall=True),
                    _card("Output by wind direction", "Click a bar to select a sector",
                          dcc.Graph(id="bar-chart",
                                    config={**GRAPH_CONFIG, "displayModeBar": False}),
                          controls=dcc.RadioItems(
                              id="bar-metric", value="mean", inline=True, className="segmented",
                              options=[{"label": "Mean kW", "value": "mean"},
                                       {"label": "Energy", "value": "energy"}]),
                          class_name="card-bar", tall=True),
                    _card("Monthly trend", "Mean active power by month · drag across months to brush",
                          dcc.Graph(id="line-chart",
                                    config={**GRAPH_CONFIG, "displayModeBar": False}),
                          class_name="card-line"),
                ]),
            ]),
        ]),
    ])
