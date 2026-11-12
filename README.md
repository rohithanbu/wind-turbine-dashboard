# Wind Turbine Performance Dashboard

Interactive Plotly Dash dashboard for the [Wind Turbine SCADA dataset](https://www.kaggle.com/datasets/berkerisen/wind-turbine-scada-dataset).
It has three linked views (power curve, sector bars, monthly trend) with cross-filtering and a KPI row.

**Live prototype:** _add the Render URL here after deploying_

![Default view](screenshots/dashboard-default.png)
![Cross-filtered: North-east sector, underperforming readings only](screenshots/dashboard-filtered.png)

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py                     # http://127.0.0.1:8050
```

`data/T1.csv` is included in the repository. To re-download it from Kaggle, run
`python scripts/download_data.py`.

## Research questions and views

| # | Research question | Answered by |
|---|---|---|
| RQ1 | How does active power correlate with wind speed, and at what wind speed does the power curve flatten? | **Power curve** scatter (with theoretical curve and plateau marker) |
| RQ2 | Which wind direction sectors yield the most power, and does this change across months? | **Output by wind direction** bars, linked to the **Monthly trend** line (one line per selected sector) |
| RQ3 | When cross-filtering by low-performance periods, do anomalies appear between theoretical and actual power? | **Performance** filter ("Underperforming only") applied to all three views and the KPI row |

## Data preparation

Source: `T1.csv`, 50,530 rows at 10-minute intervals from 1 Jan to 31 Dec 2018, from a single turbine.
The full file is loaded and every filter and KPI uses all rows. All preparation is in
[`dashboard/data.py`](dashboard/data.py):

| Step | What and why |
|---|---|
| Column renaming | The 5 raw columns are renamed by position (`timestamp`, `active_power`, `wind_speed`, `theoretical_power`, `wind_direction`), because the degree sign in `Wind Direction (°)` is mis-encoded in the CSV. The file is read as Latin-1 for the same reason. |
| Date parsing | `Date/Time` is parsed with the explicit format `DD MM YYYY HH:MM`, and `month` (1–12) is derived from it. |
| Direction binning | Wind direction (0–360°) is binned into 8 compass sectors of 45° each (N, NE, … NW), each centred on its heading, so N covers 337.5°–22.5°. |
| Performance ratio | `perf_ratio = active_power / theoretical_power`, computed only where theoretical power is at least 100 kW. Below cut-in the denominator is near zero and the ratio would be noise. Readings below 70% (adjustable from 50–95%) count as "underperforming". |
| Negative power | 57 readings show small negative power (down to −2.5 kW), the turbine drawing power while idle. They are kept as-is in the charts and clipped to 0 when summing energy. |
| Missing intervals | 2,030 of the 52,560 expected 10-minute intervals are missing, mostly in January and September–November. They are left as gaps, not interpolated; monthly figures are means of the readings that exist. |
| Aggregation | The bar chart gives the per-sector mean power and energy (MWh = kW × 1/6 h ÷ 1000). The trend chart gives mean power per month. The theoretical curve is averaged into 0.5 m/s bins. The plateau marker is the wind speed where the binned median power first reaches 95% of its peak. |
| Scatter sampling | The scatter draws a fixed random sample of 15,000 points so the page stays responsive, and labels it as a sample on the chart. Filters, KPIs and the other views always use the full data. |

## Changes from the proposal

The channel justification table in the proposal is followed, with these changes:

| Proposal | Implementation | Reason |
|---|---|---|
| Wind direction → **colour hue** on the scatter points | The scatter shows all points in a neutral grey by default. Hue appears only for the sectors the user selects (up to 3). With more than 3 selected, the selection shares one highlight colour. | Eight hues on ~50,000 overlapping points can't be told apart, especially by colour-blind viewers, and colour noise hides the power-curve shape that RQ1 asks about. Hue still conveys identity only (expressiveness), but only where it can be read. |
| *(not in table)* | **New bar chart:** wind direction sector → **x-position** (compass order) plus the same hue; mean power or energy → **bar length** on a common zero baseline. | RQ2 compares sectors by magnitude. Position and length on a common scale are more effective than hue for that comparison (effectiveness). |
| *(not in table)* | **Theoretical power** → a **dashed line** on the scatter and on the monthly trend; actual power is solid. | RQ3 compares actual against theoretical. A shared position scale makes the gap directly readable, and line style separates expected from measured. |
| *(not in table)* | Each sector keeps **one fixed hue in every view** (e.g. North is always blue). | The bar, scatter and line views are linked, so a colour has to mean the same sector everywhere. The palette was checked for colour-vision deficiency on adjacent pairs. |

The rest matches the proposal: active power → y-position, wind speed → x-position, time (months) →
x-position flowing left to right on a line, and a side-panel layout with a KPI row.

## Interaction

- **Bar chart:** click a sector to select it in every view (it toggles the sidebar checkbox too).
- **Power curve:** drag a box to brush a wind-speed / power range; the other views and the KPIs update.
- **Monthly trend:** click a month or drag across several to filter the period.
- **Sidebar:** direction checkboxes, month range, performance mode and threshold, and **Reset all**.
- Every chart has hover tooltips; double-click a chart to clear its brush.

## Deployment (Render)

`render.yaml` defines a free Render web service: `pip install -r requirements.txt`, then
`gunicorn app:server`. In Render, choose **New → Blueprint** and point it at this repository.

## Structure

```
app.py                  entry point: builds the app, registers callbacks
dashboard/
  config.py             paths, columns, sectors, thresholds, colour system
  data.py               load + derive columns; Filters = the cross-filter state
  figures.py            pure figure builders + KPI maths (no Dash imports)
  layout.py             component tree (sidebar, KPI row, chart cards)
  callbacks.py          selections -> filter state -> views
assets/style.css        tokens, layout grid, responsive breakpoints
data/T1.csv             the dataset
scripts/download_data.py
render.yaml             Render deployment config
```
