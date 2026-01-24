# Skylight Web Display Design

**Date:** 2026-01-24
**Status:** Approved
**Goal:** Replace pygame visualization with a performant HTML/CSS/JS display that runs smoothly on Raspberry Pi Zero 2W

## Overview

Skylight displays real-time aircraft flying overhead, projected onto a ceiling via a Raspberry Pi connected to a projector. The current pygame implementation suffers from stuttering animation and dated visuals. This design migrates to web technologies for smoother, more polished rendering.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Raspberry Pi Zero 2W                   │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │    Python    │     │    HTTP      │     │  Chromium   │ │
│  │   Service    │────▶│   Server     │────▶│   Kiosk     │ │
│  │              │     │              │     │             │ │
│  │ - Fetch API  │     │ serves:      │     │ - Render    │ │
│  │ - Process    │     │ - index.html │     │ - Animate   │ │
│  │ - Write JSON │     │ - flights.json│    │ - Poll JSON │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│         │                                         ▲        │
│         ▼                                         │        │
│  ┌──────────────┐                                 │        │
│  │flights.json  │─────────────────────────────────┘        │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

**Two processes:**
1. **Python service** - Fetches from OpenSky API, processes data, writes `flights.json`
2. **Chromium kiosk** - Renders visualization, polls JSON, animates planes

## Visual Style

**Minimal/Elegant** - Clean lines, subtle grid overlay, muted colors with soft glows, gradient trails that fade smoothly.

Key visual elements:
- Deep night sky gradient background
- Subtle grid pattern
- SVG plane icons with glow effects
- Long gradient trails showing flight path history
- Clean, understated labels (callsign + country)
- Minimal UI (plane count, compass indicator)

## Configuration

All tunable values in a single `config.py`:

```python
# config.py

# ─── Data Fetching ─────────────────────────────────
API_INTERVAL = 15          # Seconds between OpenSky requests
API_TIMEOUT = 10           # Request timeout

# ─── Geographic Bounds ─────────────────────────────
HOME_LAT = 51.4230
HOME_LON = -0.0542
SEARCH_RADIUS_KM = 25
MAX_ALTITUDE_M = 12000

# ─── Display Limits ────────────────────────────────
MAX_PLANES = 8             # Maximum planes shown at once
TRAIL_POINTS = 200         # Position history per plane
PLANE_TIMEOUT_S = 60       # Keep plane after leaving radar

# ─── Rendering ─────────────────────────────────────
POLL_INTERVAL_MS = 1500    # Browser JSON poll rate
SMOOTHING_FACTOR = 0.08    # Position interpolation (0-1)
TRAIL_FADE_STEPS = 50      # Gradient stops in trail

# ─── Platform Detection ────────────────────────────
import platform
IS_PI = platform.machine().startswith('aarch64')
```

Browser receives shared values via generated `config.json`.

## Data Format

`flights.json` structure:

```json
{
  "updated": "2026-01-24T14:32:15Z",
  "status": "ok",
  "home": { "lat": 51.4230, "lon": -0.0542 },
  "planes": [
    {
      "id": "4ca8a3",
      "callsign": "BA284",
      "country": "United Kingdom",
      "position": { "lat": 51.4891, "lon": -0.1132 },
      "altitude_m": 10200,
      "heading": 247,
      "velocity_mps": 245,
      "trail": [
        { "lat": 51.4512, "lon": -0.0821, "age": 0 },
        { "lat": 51.4634, "lon": -0.0956, "age": 15 }
      ],
      "color": "#64b5f6",
      "last_seen": "2026-01-24T14:32:15Z",
      "extrapolated": false
    }
  ]
}
```

**Status values:**
- `"ok"` - Data fresh, API working
- `"no_data"` - API returned empty (no planes in area)
- `"stale"` - API failed, showing last known data
- `"error"` - Persistent failure

## Browser Implementation

### File Structure

```
web/
├── index.html        # Single page, minimal markup
├── styles.css        # All visual styling
├── app.js            # Data fetching, rendering logic
└── config.json       # Generated from Python config
```

### Animation Strategy

**Velocity-based extrapolation** for consistent motion:

1. On data update - Store plane's `heading`, `velocity_mps`, and `position`
2. Every frame - Move plane forward: `distance = velocity × deltaTime`
3. On next update - Blend from extrapolated position to real position over ~300ms

This ensures planes move at consistent speeds regardless of how far apart data points are.

### Rendering Approach

- CSS transforms for all movement (GPU-accelerated)
- `will-change: transform` on plane elements
- Canvas element per plane for gradient trails
- Minimal DOM elements (~24 total for 8 planes)
- No JavaScript animation loops at 60fps - rely on CSS transitions where possible

## Connection States

| State | Trigger | Display |
|-------|---------|---------|
| **Connected** | `status: "ok"` | Normal view |
| **No aircraft** | Empty `planes` array | "Clear skies" message |
| **Disconnected** | JSON fetch fails | "Reconnecting..." overlay, planes frozen |

Reconnection: Retry every 5 seconds until successful.

## Plane Lifecycle

When a plane leaves the radar area:

1. Plane stops appearing in API response
2. Python keeps plane for `PLANE_TIMEOUT_S` (60s default)
3. Position extrapolated using last known heading/velocity
4. `extrapolated: true` flag set in JSON
5. After timeout, plane removed from JSON
6. Browser can fade out extrapolated planes for visual polish

Trail cleanup: Capped at `TRAIL_POINTS` (200 default) per plane.

## Deployment

### Pi Setup

- Raspberry Pi OS Lite (no desktop)
- Chromium for kiosk display
- Python 3 for data service
- systemd manages both services

### Services

```ini
# skylight-data.service
[Service]
ExecStart=/usr/bin/python3 fetch_flights.py
Restart=always
```

```ini
# skylight-display.service
[Service]
ExecStart=/usr/bin/chromium-browser --kiosk http://localhost:8000
Restart=always
```

### Development Workflow

1. Develop on Mac (same Python + browser code)
2. Test locally with `./dev.sh`
3. Deploy with `./deploy.sh` (rsync + service restart)

## File Structure

```
skylight/
├── config.py              # Shared configuration
├── fetch_flights.py       # Python data service
├── web/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── config.json
├── deploy/
│   ├── skylight-data.service
│   ├── skylight-display.service
│   └── setup-pi.sh
├── dev.sh                 # Local development
└── deploy.sh              # Push to Pi
```

## Next Steps

1. Create implementation plan with detailed tasks
2. Set up git worktree for isolated development
3. Implement Python data service
4. Implement browser visualization
5. Test on Pi Zero 2W
6. Refine visual details (plane orientation, trail fades)
