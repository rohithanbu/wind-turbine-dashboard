"""Central configuration: paths, column names, sector definitions and the colour system.

Everything visual that more than one module needs lives here, so a sector keeps the
same hue in every view (colour follows the entity, never its rank).
"""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT_DIR / "data" / "T1.csv"

# The raw headers are renamed positionally - the degree sign in "Wind Direction (°)"
# is mis-encoded in the CSV, so matching on names is fragile.
COLUMNS = ["timestamp", "active_power", "wind_speed", "theoretical_power", "wind_direction"]

INTERVAL_HOURS = 10 / 60  # SCADA logs one row every 10 minutes

# --- Wind direction sectors -------------------------------------------------
# Eight 45° compass sectors, each centred on its heading (N = 337.5°-22.5°).
SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SECTOR_NAMES = {
    "N": "North", "NE": "North-east", "E": "East", "SE": "South-east",
    "S": "South", "SW": "South-west", "W": "West", "NW": "North-west",
}

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# --- Performance definition -------------------------------------------------
# A reading is "underperforming" when actual output falls below a share of the
# theoretical curve. Readings where the curve itself is near zero (below cut-in)
# are excluded so tiny denominators don't produce noise.
MIN_THEORETICAL_KW = 100
DEFAULT_PERF_THRESHOLD = 0.70

# --- Rendering limits -------------------------------------------------------
# The scatter draws at most this many points (a fixed random sample) so updates
# stay fast; filters and KPIs always use the full data.
MAX_SCATTER_POINTS = 15_000
# The scatter only gives each highlighted sector its own hue for up to 3 sectors:
# beyond that, overlapping dots can't be told apart reliably by colour-blind readers.
MAX_HUED_SECTORS = 3

# --- Colour system ----------------------------------------------------------
# Categorical slots in fixed order (validated for colour-vision deficiency on
# adjacent pairs). N takes slot 1 (blue), so "North" is blue everywhere.
SECTOR_COLORS = dict(zip(SECTORS, [
    "#2a78d6",  # N  blue
    "#eb6834",  # NE orange
    "#1baf7a",  # E  aqua
    "#eda100",  # SE yellow
    "#e87ba4",  # S  magenta
    "#008300",  # SW green
    "#6250d6",  # W  violet
    "#e34948",  # NW red
]))

COLORS = {
    "surface": "#fcfcfb",       # card / chart surface
    "page": "#f9f9f7",          # page plane
    "ink": "#0b0b0b",           # primary text, key series
    "ink_secondary": "#52514e",
    "muted": "#898781",         # axis labels, reference lines
    "context": "#c3c2b7",       # de-emphasised data (unselected points)
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "brush": "rgba(42, 120, 214, 0.08)",  # selected month band
}

FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", sans-serif'
