"""Entry point: python app.py, then open http://127.0.0.1:8050"""
from dash import Dash

from dashboard.callbacks import register_callbacks
from dashboard.data import load_data
from dashboard.layout import build_layout

app = Dash(__name__, title="Wind Turbine Performance")
app.layout = build_layout(load_data())
register_callbacks(app)
server = app.server  # exposed for a WSGI server (e.g. gunicorn app:server)

if __name__ == "__main__":
    app.run(debug=True)
