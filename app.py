"""Entry point: python app.py, then open http://127.0.0.1:8050"""
from dash import Dash

from dashboard.callbacks import register_callbacks
from dashboard.data import load_data
from dashboard.layout import build_layout

# serve_locally=False loads Dash/Plotly JavaScript (Plotly alone is ~4.7 MB) from the
# public CDN, compressed and cached, instead of uncompressed from this small server.
app = Dash(__name__, title="Wind Turbine Performance", serve_locally=False)
app.layout = build_layout(load_data())
register_callbacks(app)
server = app.server  # exposed for a WSGI server (e.g. gunicorn app:server)

if __name__ == "__main__":
    app.run(debug=True)
