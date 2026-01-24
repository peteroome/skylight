# config.py
"""Shared configuration for Skylight flight display."""

import platform

# ─── Data Fetching ─────────────────────────────────
API_URL = "https://opensky-network.org/api/states/all"
API_INTERVAL_S = 15
API_TIMEOUT_S = 10

# ─── Geographic Bounds ─────────────────────────────
HOME_LAT = 51.4229712
HOME_LON = -0.0541772
LAT_SPAN = 0.12
LON_SPAN = 0.34

# Calculated bounds
MIN_LAT = HOME_LAT - LAT_SPAN
MAX_LAT = HOME_LAT + LAT_SPAN
MIN_LON = HOME_LON - LON_SPAN
MAX_LON = HOME_LON + LON_SPAN

# ─── Filtering ─────────────────────────────────────
MAX_ALTITUDE_M = 12000
MAX_PLANES = 8

# ─── Plane Lifecycle ───────────────────────────────
TRAIL_POINTS = 200
PLANE_TIMEOUT_S = 60

# ─── Browser Rendering ─────────────────────────────
POLL_INTERVAL_MS = 1500
SMOOTHING_FACTOR = 0.08
TRAIL_FADE_STEPS = 50

# ─── Colors (hex for browser) ──────────────────────
PLANE_COLORS = [
    "#64b5f6",  # Blue
    "#81c784",  # Green
    "#ffb74d",  # Orange
    "#f06292",  # Pink
    "#ba68c8",  # Purple
    "#4dd0e1",  # Cyan
    "#fff176",  # Yellow
    "#a1887f",  # Brown
]

# ─── Paths ─────────────────────────────────────────
DATA_FILE = "web/flights.json"
CONFIG_FILE = "web/config.json"

# ─── Platform Detection ────────────────────────────
IS_PI = platform.machine().startswith("aarch64") or platform.machine().startswith("arm")
