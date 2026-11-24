"""All interactivity.

Data flow (one source of truth per filter):

    wind-rose click ─────► sector-filter (Checklist)  ┐
    line click / brush ──► month-filter (RangeSlider) ├─► every figure + KPIs
    scatter brush ───────► scatter-range (Store)      │
    perf-mode / threshold (sidebar) ──────────────────┘

Each figure applies the *other* views' filters and only highlights its own
selection (Filters.without), the standard cross-filter behaviour.
"""
from __future__ import annotations

from dash import Dash, Input, Output, State, ctx
from dash.exceptions import PreventUpdate

from .config import DEFAULT_PERF_THRESHOLD, LOW_COUNT_WARNING, SECTORS
from .data import Filters, load_data, theoretical_curve
from .figures import (
    compute_kpis, line_figure, line_title, plateau_wind_speed, power_curve_title, rose_figure,
    rose_title, scatter_figure, sector_summary,
)

# The full filter state, in Filters.from_inputs argument order.
FILTER_INPUTS = [
    Input("sector-filter", "value"),
    Input("month-filter", "value"),
    Input("scatter-range", "data"),
    Input("perf-mode", "value"),
    Input("perf-threshold", "value"),
]


def register_callbacks(app: Dash) -> None:
    df = load_data()
    curve = theoretical_curve()

    # Warm-up: Plotly imports its validators lazily on first use (about a second), so
    # build each figure once at start-up instead of on the first visitor's request.
    scatter_figure(df.head(2000), curve, (), None)
    line_figure(df, (), (1, 12))
    rose_figure(sector_summary(df), (), "mean")

    # --- Selections -> filter state ----------------------------------------

    # Runs in the browser: reduces the scatter's selectedData (which lists every
    # selected point - thousands of them) to just the box range, so only a tiny
    # payload ever reaches the server.
    app.clientside_callback(
        """
        function(selected, resetClicks, current) {
            const triggered = dash_clientside.callback_context.triggered.map(t => t.prop_id);
            if (triggered.includes("reset-button.n_clicks")) { return null; }
            const range = selected && selected.range
                ? {x: selected.range.x, y: selected.range.y} : null;
            if (JSON.stringify(range) === JSON.stringify(current || null)) {
                return dash_clientside.no_update;
            }
            return range;
        }
        """,
        Output("scatter-range", "data"),
        Input("scatter-chart", "selectedData"),
        Input("reset-button", "n_clicks"),
        State("scatter-range", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("sector-filter", "value"),
        Output("rose-chart", "clickData"),
        Input("rose-chart", "clickData"),
        Input("reset-button", "n_clicks"),
        State("sector-filter", "value"),
        prevent_initial_call=True,
    )
    def toggle_sector(click, _reset, current):
        """Clicking a wind-rose wedge toggles that sector in the sidebar checklist."""
        if ctx.triggered_id == "reset-button":
            return [], None
        if not click:
            raise PreventUpdate
        sector = click["points"][0]["customdata"][0]
        chosen = set(current or [])
        chosen ^= {sector}
        # Clearing clickData lets the same wedge be clicked twice in a row.
        return [s for s in SECTORS if s in chosen], None

    @app.callback(
        Output("month-filter", "value"),
        Output("line-chart", "clickData"),
        Input("line-chart", "clickData"),
        Input("line-chart", "selectedData"),
        Input("reset-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def brush_months(click, selected, _reset):
        """Click a month or brush a span of months on the trend chart."""
        prop = ctx.triggered[0]["prop_id"]
        if ctx.triggered_id == "reset-button":
            return [1, 12], None
        if prop.endswith("clickData") and click:
            month = int(round(click["points"][0]["x"]))
            return [month, month], None
        if prop.endswith("selectedData") and selected and selected.get("range"):
            # Month m occupies [m - 0.5, m + 0.5] on the axis.
            x0, x1 = sorted(selected["range"]["x"])
            start, end = max(1, round(x0)), min(12, round(x1))
            if start > end:
                raise PreventUpdate
            return [start, end], None
        # Deselect (double-click) leaves the slider as is; "Reset all" clears it.
        raise PreventUpdate

    @app.callback(
        Output("perf-threshold", "disabled"),
        Input("perf-mode", "value"),
    )
    def toggle_threshold(mode):
        return mode == "all"

    @app.callback(
        Output("perf-mode", "value"),
        Output("perf-threshold", "value"),
        Input("reset-button", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_performance(_reset):
        """'Reset all' also returns the performance filter to its defaults."""
        return "all", round(DEFAULT_PERF_THRESHOLD * 100)

    # --- Filter state -> views --------------------------------------------

    @app.callback(Output("scatter-chart", "figure"), Output("scatter-title", "children"), *FILTER_INPUTS)
    def update_scatter(sectors, months, scatter_range, perf_mode, threshold):
        # The user's own brush is already drawn by Plotly; re-rendering 15k
        # points just to redraw it would only add lag.
        if ctx.triggered_id == "scatter-range" and scatter_range is not None:
            raise PreventUpdate
        filters = Filters.from_inputs(sectors, months, scatter_range, perf_mode, threshold)
        view = filters.without("scatter").without("sector").apply(df)
        # A median or plateau of underperforming readings alone isn't the turbine's curve.
        typical = filters.perf_mode != "under"
        plateau = plateau_wind_speed(view) if typical else None
        figure = scatter_figure(view, curve, filters.sectors, scatter_range,
                                plateau=plateau, show_median=typical)
        return figure, power_curve_title(plateau, filters.perf_mode)

    @app.callback(Output("line-chart", "figure"), Output("line-title", "children"), *FILTER_INPUTS)
    def update_line(sectors, months, scatter_range, perf_mode, threshold):
        filters = Filters.from_inputs(sectors, months, scatter_range, perf_mode, threshold)
        # Sectors split the line into one series each rather than filtering.
        view = filters.without("month").without("sector").apply(df)
        return line_figure(view, filters.sectors, filters.months), line_title(view, filters.sectors)

    @app.callback(Output("rose-chart", "figure"), Output("rose-title", "children"),
                  *FILTER_INPUTS, Input("rose-metric", "value"))
    def update_rose(sectors, months, scatter_range, perf_mode, threshold, metric):
        filters = Filters.from_inputs(sectors, months, scatter_range, perf_mode, threshold)
        summary = sector_summary(filters.without("sector").apply(df))
        return rose_figure(summary, filters.sectors, metric), rose_title(summary, metric)

    @app.callback(
        Output("kpi-energy", "children"),
        Output("kpi-max-wind", "children"),
        Output("kpi-active", "children"),
        Output("kpi-efficiency", "children"),
        Output("reading-count", "children"),
        Output("reading-count", "className"),
        *FILTER_INPUTS,
    )
    def update_kpis(sectors, months, scatter_range, perf_mode, threshold):
        """KPIs summarise the intersection of every active filter."""
        view = Filters.from_inputs(sectors, months, scatter_range, perf_mode, threshold).apply(df)
        kpis = compute_kpis(view)
        count = f"Showing {len(view):,} of {len(df):,} readings"
        css = "reading-count"
        # Empty state: say so plainly instead of leaving a near-empty dashboard unexplained.
        if view.empty:
            count = "No readings match the current filters. Use Reset all to start over."
            css += " is-warning"
        elif len(view) < LOW_COUNT_WARNING:
            count += (" (very few match the current filters, so results may not be representative;"
                      " use Reset all to see the full year)")
            css += " is-warning"
        return kpis["energy"], kpis["max_wind"], kpis["active"], kpis["efficiency"], count, css
