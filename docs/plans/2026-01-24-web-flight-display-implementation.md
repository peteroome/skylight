# Web Flight Display Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the pygame flight visualization with an HTML/CSS/JS frontend that runs smoothly on Raspberry Pi Zero 2W.

**Architecture:** Python service fetches flight data from OpenSky API and writes to a JSON file. Browser polls the JSON and renders planes with CSS-animated trails. Velocity-based extrapolation keeps motion smooth between data updates.

**Tech Stack:** Python 3 (data service), vanilla HTML/CSS/JS (no frameworks), systemd (Pi deployment)

---

## Task 1: Create Configuration Module

**Files:**
- Create: `config.py`

**Step 1: Create config file with all tunable values**

```python
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
```

**Step 2: Verify config imports correctly**

Run: `python3 -c "import config; print(f'Home: {config.HOME_LAT}, {config.HOME_LON}')"`
Expected: `Home: 51.4229712, -0.0541772`

**Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add shared configuration module"
```

---

## Task 2: Create Flight Data Service

**Files:**
- Create: `fetch_flights.py`

**Step 1: Create the data fetching service**

```python
#!/usr/bin/env python3
"""Fetch flight data from OpenSky and write to JSON for browser consumption."""

import json
import math
import time
from datetime import datetime, timezone
from collections import deque
from pathlib import Path

import requests

import config

# In-memory flight state
flights: dict = {}
color_index = 0


def fetch_from_api() -> list | None:
    """Fetch current flights from OpenSky Network API."""
    try:
        response = requests.get(
            config.API_URL,
            params={
                "lamin": config.MIN_LAT,
                "lamax": config.MAX_LAT,
                "lomin": config.MIN_LON,
                "lomax": config.MAX_LON,
            },
            timeout=config.API_TIMEOUT_S,
        )
        if response.status_code == 200:
            states = response.json().get("states")
            return states if states else []
        print(f"API returned status {response.status_code}")
        return None
    except requests.RequestException as e:
        print(f"API error: {e}")
        return None


def distance_from_home(lat: float, lon: float) -> float:
    """Calculate squared distance from home (for sorting, no sqrt needed)."""
    dlat = lat - config.HOME_LAT
    dlon = lon - config.HOME_LON
    return dlat * dlat + dlon * dlon


def extrapolate_position(flight: dict, dt_seconds: float) -> tuple[float, float]:
    """Project position forward based on velocity and heading."""
    lat, lon = flight["lat"], flight["lon"]
    velocity = flight["velocity_mps"]
    heading = flight["heading"]

    if velocity <= 0:
        return lat, lon

    heading_rad = math.radians(heading)
    cos_lat = math.cos(math.radians(lat))

    # Convert m/s to degrees/s
    lat_speed = velocity * math.cos(heading_rad) / 111000
    lon_speed = velocity * math.sin(heading_rad) / (111000 * cos_lat)

    return lat + lat_speed * dt_seconds, lon + lon_speed * dt_seconds


def process_states(states: list, now: datetime) -> None:
    """Process raw API states into flight records."""
    global color_index

    for state in states:
        # Skip if missing position
        if state[5] is None or state[6] is None:
            continue

        icao = state[0]
        callsign = (state[1] or "").strip()
        country = state[2] or "Unknown"
        lon, lat = state[5], state[6]
        altitude = state[7] or 0
        velocity = state[9] or 0
        heading = state[10] or 0

        # Filter by altitude
        if altitude > config.MAX_ALTITUDE_M:
            continue

        if icao not in flights:
            # New flight - assign color
            color = config.PLANE_COLORS[color_index % len(config.PLANE_COLORS)]
            color_index += 1

            flights[icao] = {
                "id": icao,
                "callsign": callsign,
                "country": country,
                "lat": lat,
                "lon": lon,
                "altitude_m": altitude,
                "heading": heading,
                "velocity_mps": velocity,
                "color": color,
                "trail": deque(maxlen=config.TRAIL_POINTS),
                "last_seen": now,
                "extrapolated": False,
            }
        else:
            # Update existing flight
            f = flights[icao]
            f["callsign"] = callsign
            f["country"] = country
            f["lat"] = lat
            f["lon"] = lon
            f["altitude_m"] = altitude
            f["heading"] = heading
            f["velocity_mps"] = velocity
            f["last_seen"] = now
            f["extrapolated"] = False

        # Add to trail
        flights[icao]["trail"].append({
            "lat": lat,
            "lon": lon,
            "time": now.isoformat(),
        })


def prune_stale_flights(now: datetime) -> None:
    """Remove flights not seen within timeout, extrapolate others."""
    to_remove = []

    for icao, f in flights.items():
        age_seconds = (now - f["last_seen"]).total_seconds()

        if age_seconds > config.PLANE_TIMEOUT_S:
            to_remove.append(icao)
        elif age_seconds > config.API_INTERVAL_S:
            # Flight missing from latest update - extrapolate
            f["extrapolated"] = True
            new_lat, new_lon = extrapolate_position(f, config.API_INTERVAL_S)
            f["lat"] = new_lat
            f["lon"] = new_lon
            f["trail"].append({
                "lat": new_lat,
                "lon": new_lon,
                "time": now.isoformat(),
            })

    for icao in to_remove:
        del flights[icao]
        print(f"Removed stale flight: {icao}")


def build_output(now: datetime, status: str) -> dict:
    """Build the JSON output structure."""
    # Sort by distance, take closest
    sorted_flights = sorted(
        flights.values(),
        key=lambda f: distance_from_home(f["lat"], f["lon"])
    )
    visible = sorted_flights[:config.MAX_PLANES]

    # Convert trails to serializable format with age
    planes = []
    for f in visible:
        trail_with_age = []
        for point in f["trail"]:
            point_time = datetime.fromisoformat(point["time"])
            age_seconds = (now - point_time).total_seconds()
            trail_with_age.append({
                "lat": point["lat"],
                "lon": point["lon"],
                "age": round(age_seconds, 1),
            })

        planes.append({
            "id": f["id"],
            "callsign": f["callsign"],
            "country": f["country"],
            "position": {"lat": f["lat"], "lon": f["lon"]},
            "altitude_m": f["altitude_m"],
            "heading": f["heading"],
            "velocity_mps": f["velocity_mps"],
            "trail": trail_with_age,
            "color": f["color"],
            "last_seen": f["last_seen"].isoformat(),
            "extrapolated": f["extrapolated"],
        })

    return {
        "updated": now.isoformat(),
        "status": status,
        "home": {"lat": config.HOME_LAT, "lon": config.HOME_LON},
        "planes": planes,
    }


def write_json(data: dict) -> None:
    """Write data to JSON file atomically."""
    path = Path(config.DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file then rename (atomic on POSIX)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        json.dump(data, f, indent=2)
    temp_path.rename(path)


def write_browser_config() -> None:
    """Write config values needed by browser."""
    browser_config = {
        "pollIntervalMs": config.POLL_INTERVAL_MS,
        "smoothingFactor": config.SMOOTHING_FACTOR,
        "trailFadeSteps": config.TRAIL_FADE_STEPS,
        "home": {"lat": config.HOME_LAT, "lon": config.HOME_LON},
        "bounds": {
            "minLat": config.MIN_LAT,
            "maxLat": config.MAX_LAT,
            "minLon": config.MIN_LON,
            "maxLon": config.MAX_LON,
        },
    }

    path = Path(config.CONFIG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(browser_config, f, indent=2)


def main() -> None:
    """Main loop: fetch, process, write, repeat."""
    print("Skylight data service starting...")
    print(f"Home: {config.HOME_LAT}, {config.HOME_LON}")
    print(f"Bounds: {config.MIN_LAT}-{config.MAX_LAT}, {config.MIN_LON}-{config.MAX_LON}")

    # Write browser config once at startup
    write_browser_config()
    print(f"Wrote browser config to {config.CONFIG_FILE}")

    last_success = None

    while True:
        now = datetime.now(timezone.utc)
        states = fetch_from_api()

        if states is not None:
            process_states(states, now)
            last_success = now
            status = "ok" if flights else "no_data"
            print(f"[{now.strftime('%H:%M:%S')}] Tracking {len(flights)} flights")
        else:
            status = "stale" if last_success else "error"
            print(f"[{now.strftime('%H:%M:%S')}] API failed, status: {status}")

        prune_stale_flights(now)
        output = build_output(now, status)
        write_json(output)

        time.sleep(config.API_INTERVAL_S)


if __name__ == "__main__":
    main()
```

**Step 2: Test the service runs and produces JSON**

Run: `timeout 20 python3 fetch_flights.py || true && cat web/flights.json | head -30`
Expected: JSON output with `updated`, `status`, `home`, and `planes` fields

**Step 3: Commit**

```bash
git add fetch_flights.py
git commit -m "feat: add flight data fetching service"
```

---

## Task 3: Create Web Directory Structure and HTML

**Files:**
- Create: `web/index.html`

**Step 1: Create the HTML structure**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Skylight</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <div id="sky">
    <div class="grid"></div>
    <div id="planes"></div>

    <div class="status" id="status">
      <span class="status-count" id="count">0</span>
      <span class="status-label">aircraft overhead</span>
    </div>

    <div class="compass">
      <span class="compass-n">N</span>
    </div>

    <div class="overlay" id="overlay">
      <div class="overlay-content">
        <div class="overlay-spinner"></div>
        <div class="overlay-text" id="overlay-text">Connecting...</div>
      </div>
    </div>
  </div>

  <script src="app.js"></script>
</body>
</html>
```

**Step 2: Verify file exists**

Run: `cat web/index.html | head -10`
Expected: DOCTYPE and html tags visible

**Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat: add HTML structure for flight display"
```

---

## Task 4: Create CSS Styles

**Files:**
- Create: `web/styles.css`

**Step 1: Create the stylesheet**

```css
/* web/styles.css */

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: linear-gradient(180deg, #0a0f1a 0%, #1a2332 50%, #0d1420 100%);
  min-height: 100vh;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
}

#sky {
  position: fixed;
  inset: 0;
}

/* Subtle grid overlay */
.grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.015) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.015) 1px, transparent 1px);
  background-size: 80px 80px;
  pointer-events: none;
}

/* Plane container */
#planes {
  position: absolute;
  inset: 0;
}

.plane {
  position: absolute;
  will-change: transform;
  transition: none; /* JS handles animation */
}

/* Trail canvas */
.plane-trail {
  position: absolute;
  pointer-events: none;
}

/* Plane icon */
.plane-icon {
  position: relative;
  width: 28px;
  height: 28px;
  filter: drop-shadow(0 0 8px var(--plane-color));
}

.plane-icon svg {
  width: 100%;
  height: 100%;
  fill: var(--plane-color);
}

/* Label */
.plane-label {
  position: absolute;
  top: 32px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.3px;
  color: var(--plane-color);
  opacity: 0.8;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

/* Status display */
.status {
  position: fixed;
  bottom: 40px;
  left: 40px;
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  letter-spacing: 0.5px;
}

.status-count {
  font-size: 32px;
  font-weight: 200;
  color: rgba(255, 255, 255, 0.7);
  display: block;
  margin-bottom: 4px;
}

.status-label {
  text-transform: uppercase;
  letter-spacing: 1px;
  font-size: 10px;
}

/* Compass */
.compass {
  position: fixed;
  bottom: 40px;
  right: 40px;
  width: 50px;
  height: 50px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.compass-n {
  position: absolute;
  top: 6px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 1px;
}

/* Connection overlay */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(10, 15, 26, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.3s, visibility 0.3s;
  z-index: 100;
}

.overlay.visible {
  opacity: 1;
  visibility: visible;
}

.overlay-content {
  text-align: center;
  color: rgba(255, 255, 255, 0.6);
}

.overlay-spinner {
  width: 40px;
  height: 40px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-top-color: rgba(255, 255, 255, 0.4);
  border-radius: 50%;
  margin: 0 auto 16px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.overlay-text {
  font-size: 14px;
  letter-spacing: 1px;
}

/* Clear skies state */
.clear-skies {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: rgba(255, 255, 255, 0.3);
  display: none;
}

.clear-skies.visible {
  display: block;
}

.clear-skies-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.clear-skies-text {
  font-size: 14px;
  letter-spacing: 1px;
  text-transform: uppercase;
}
```

**Step 2: Verify file exists**

Run: `wc -l web/styles.css`
Expected: ~170 lines

**Step 3: Commit**

```bash
git add web/styles.css
git commit -m "feat: add CSS styles for flight display"
```

---

## Task 5: Create JavaScript Application - Part 1 (Configuration and State)

**Files:**
- Create: `web/app.js`

**Step 1: Create initial app.js with configuration loading and state management**

```javascript
// web/app.js

// ─── State ────────────────────────────────────────
let config = null;
let planes = new Map(); // id -> plane state
let lastUpdate = null;
let isConnected = false;

// ─── DOM Elements ─────────────────────────────────
const planesContainer = document.getElementById('planes');
const countEl = document.getElementById('count');
const overlayEl = document.getElementById('overlay');
const overlayTextEl = document.getElementById('overlay-text');

// ─── Configuration ────────────────────────────────
async function loadConfig() {
  try {
    const response = await fetch('config.json');
    config = await response.json();
    console.log('Config loaded:', config);
    return true;
  } catch (e) {
    console.error('Failed to load config:', e);
    // Use defaults
    config = {
      pollIntervalMs: 1500,
      smoothingFactor: 0.08,
      trailFadeSteps: 50,
      home: { lat: 51.4229712, lon: -0.0541772 },
      bounds: {
        minLat: 51.3029712,
        maxLat: 51.5429712,
        minLon: -0.3941772,
        maxLon: 0.2858228,
      },
    };
    return true;
  }
}

// ─── Coordinate Conversion ────────────────────────
function latLonToScreen(lat, lon) {
  const { minLat, maxLat, minLon, maxLon } = config.bounds;
  const x = ((lon - minLon) / (maxLon - minLon)) * window.innerWidth;
  const y = (1 - (lat - minLat) / (maxLat - minLat)) * window.innerHeight;
  return { x, y };
}

// ─── Overlay Control ──────────────────────────────
function showOverlay(message) {
  overlayTextEl.textContent = message;
  overlayEl.classList.add('visible');
}

function hideOverlay() {
  overlayEl.classList.remove('visible');
}

// ─── Update Count Display ─────────────────────────
function updateCount(count) {
  countEl.textContent = count;
}
```

**Step 2: Verify syntax is valid**

Run: `node --check web/app.js && echo "Syntax OK"`
Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat: add app.js with config loading and state management"
```

---

## Task 6: Create JavaScript Application - Part 2 (Plane Rendering)

**Files:**
- Modify: `web/app.js`

**Step 1: Add plane rendering functions to app.js**

Append to `web/app.js`:

```javascript

// ─── SVG Plane Icon ───────────────────────────────
const PLANE_SVG = `
<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
  <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
</svg>
`;

// ─── Create Plane Element ─────────────────────────
function createPlaneElement(id, color) {
  const el = document.createElement('div');
  el.className = 'plane';
  el.id = `plane-${id}`;
  el.style.setProperty('--plane-color', color);

  // Trail canvas
  const canvas = document.createElement('canvas');
  canvas.className = 'plane-trail';
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  el.appendChild(canvas);

  // Icon container
  const icon = document.createElement('div');
  icon.className = 'plane-icon';
  icon.innerHTML = PLANE_SVG;
  el.appendChild(icon);

  // Label
  const label = document.createElement('div');
  label.className = 'plane-label';
  el.appendChild(label);

  planesContainer.appendChild(el);
  return el;
}

// ─── Draw Trail on Canvas ─────────────────────────
function drawTrail(canvas, trail, color) {
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (trail.length < 2) return;

  // Parse color to RGB
  const rgb = hexToRgb(color);
  if (!rgb) return;

  // Draw trail segments with fading opacity
  for (let i = 0; i < trail.length - 1; i++) {
    const p1 = trail[i];
    const p2 = trail[i + 1];

    // Fade based on position in trail (older = dimmer)
    const progress = i / (trail.length - 1);
    const alpha = 0.1 + progress * 0.5;

    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.strokeStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
    ctx.lineWidth = 3 + progress * 4; // Thicker toward plane
    ctx.lineCap = 'round';
    ctx.stroke();
  }
}

// ─── Hex to RGB Helper ────────────────────────────
function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  } : null;
}

// ─── Update Plane Element ─────────────────────────
function updatePlaneElement(el, state) {
  const { x, y } = state.screenPos;
  const heading = state.heading;

  // Position the plane
  el.style.transform = `translate(${x}px, ${y}px)`;

  // Rotate icon to match heading
  const icon = el.querySelector('.plane-icon');
  icon.style.transform = `translate(-50%, -50%) rotate(${heading}deg)`;

  // Update label
  const label = el.querySelector('.plane-label');
  const displayName = state.callsign || state.id.toUpperCase();
  label.textContent = `${displayName} · ${state.country}`;

  // Draw trail
  const canvas = el.querySelector('.plane-trail');
  drawTrail(canvas, state.trail, state.color);
}

// ─── Remove Plane Element ─────────────────────────
function removePlaneElement(id) {
  const el = document.getElementById(`plane-${id}`);
  if (el) {
    el.remove();
  }
}
```

**Step 2: Verify syntax is valid**

Run: `node --check web/app.js && echo "Syntax OK"`
Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat: add plane rendering functions"
```

---

## Task 7: Create JavaScript Application - Part 3 (Animation Loop)

**Files:**
- Modify: `web/app.js`

**Step 1: Add animation loop and velocity extrapolation**

Append to `web/app.js`:

```javascript

// ─── Velocity Extrapolation ───────────────────────
function extrapolatePosition(state, dtSeconds) {
  if (state.velocity <= 0) return;

  const headingRad = (state.heading * Math.PI) / 180;
  const cosLat = Math.cos((state.lat * Math.PI) / 180);

  // Convert m/s to degrees/s
  const latSpeed = (state.velocity * Math.cos(headingRad)) / 111000;
  const lonSpeed = (state.velocity * Math.sin(headingRad)) / (111000 * cosLat);

  state.lat += latSpeed * dtSeconds;
  state.lon += lonSpeed * dtSeconds;
}

// ─── Animation Loop ───────────────────────────────
let lastFrameTime = 0;

function animate(currentTime) {
  if (!lastFrameTime) lastFrameTime = currentTime;
  const dtSeconds = (currentTime - lastFrameTime) / 1000;
  lastFrameTime = currentTime;

  // Cap dt to prevent huge jumps after tab switching
  const cappedDt = Math.min(dtSeconds, 0.1);

  // Update each plane
  for (const [id, state] of planes) {
    // Extrapolate position based on velocity
    extrapolatePosition(state, cappedDt);

    // Convert to screen coordinates
    const targetPos = latLonToScreen(state.lat, state.lon);

    // Smooth interpolation toward target
    if (!state.screenPos) {
      state.screenPos = targetPos;
    } else {
      const factor = config.smoothingFactor;
      state.screenPos.x += (targetPos.x - state.screenPos.x) * factor;
      state.screenPos.y += (targetPos.y - state.screenPos.y) * factor;
    }

    // Add to trail (screen coordinates)
    if (!state.trail) state.trail = [];
    const lastTrailPoint = state.trail[state.trail.length - 1];
    if (!lastTrailPoint ||
        Math.abs(state.screenPos.x - lastTrailPoint.x) > 1 ||
        Math.abs(state.screenPos.y - lastTrailPoint.y) > 1) {
      state.trail.push({ x: state.screenPos.x, y: state.screenPos.y });
      // Limit trail length
      if (state.trail.length > 300) {
        state.trail.shift();
      }
    }

    // Update DOM
    let el = document.getElementById(`plane-${id}`);
    if (!el) {
      el = createPlaneElement(id, state.color);
    }
    updatePlaneElement(el, state);
  }

  requestAnimationFrame(animate);
}
```

**Step 2: Verify syntax is valid**

Run: `node --check web/app.js && echo "Syntax OK"`
Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat: add animation loop with velocity extrapolation"
```

---

## Task 8: Create JavaScript Application - Part 4 (Data Fetching and Main Loop)

**Files:**
- Modify: `web/app.js`

**Step 1: Add data fetching and initialization**

Append to `web/app.js`:

```javascript

// ─── Fetch Flight Data ────────────────────────────
async function fetchFlightData() {
  try {
    const response = await fetch('flights.json?' + Date.now());
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    lastUpdate = new Date(data.updated);

    if (data.status === 'error') {
      if (isConnected) {
        showOverlay('Connection lost. Reconnecting...');
        isConnected = false;
      }
      return;
    }

    // Hide overlay on successful data
    if (!isConnected) {
      hideOverlay();
      isConnected = true;
    }

    // Track which planes are in the new data
    const newPlaneIds = new Set();

    // Update or create planes
    for (const planeData of data.planes) {
      newPlaneIds.add(planeData.id);

      let state = planes.get(planeData.id);
      if (!state) {
        // New plane
        state = {
          id: planeData.id,
          callsign: planeData.callsign,
          country: planeData.country,
          lat: planeData.position.lat,
          lon: planeData.position.lon,
          heading: planeData.heading,
          velocity: planeData.velocity_mps,
          color: planeData.color,
          extrapolated: planeData.extrapolated,
          trail: [], // Will build from screen positions
          screenPos: null,
        };

        // Initialize trail from data if available
        if (planeData.trail && planeData.trail.length > 0) {
          state.trail = planeData.trail.map(p => latLonToScreen(p.lat, p.lon));
        }

        planes.set(planeData.id, state);
      } else {
        // Update existing plane - blend toward new position
        state.callsign = planeData.callsign;
        state.country = planeData.country;
        state.heading = planeData.heading;
        state.velocity = planeData.velocity_mps;
        state.extrapolated = planeData.extrapolated;

        // Smoothly correct position drift
        state.lat = planeData.position.lat;
        state.lon = planeData.position.lon;
      }
    }

    // Remove planes no longer in data
    for (const [id] of planes) {
      if (!newPlaneIds.has(id)) {
        removePlaneElement(id);
        planes.delete(id);
      }
    }

    // Update count
    updateCount(data.planes.length);

  } catch (e) {
    console.error('Fetch error:', e);
    if (isConnected) {
      showOverlay('Reconnecting...');
      isConnected = false;
    }
  }
}

// ─── Main Entry Point ─────────────────────────────
async function main() {
  showOverlay('Connecting...');

  await loadConfig();

  // Start animation loop
  requestAnimationFrame(animate);

  // Initial fetch
  await fetchFlightData();

  // Poll for updates
  setInterval(fetchFlightData, config.pollIntervalMs);
}

// ─── Handle Window Resize ─────────────────────────
window.addEventListener('resize', () => {
  // Resize all trail canvases
  document.querySelectorAll('.plane-trail').forEach(canvas => {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  });

  // Clear trails to avoid distortion
  for (const state of planes.values()) {
    state.trail = [];
  }
});

// ─── Start ────────────────────────────────────────
main();
```

**Step 2: Verify syntax is valid**

Run: `node --check web/app.js && echo "Syntax OK"`
Expected: `Syntax OK`

**Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat: add data fetching and main initialization"
```

---

## Task 9: Create Development Script

**Files:**
- Create: `dev.sh`

**Step 1: Create development runner script**

```bash
#!/bin/bash
# dev.sh - Run Skylight locally for development

set -e

echo "🛫 Starting Skylight development server..."

# Kill any existing processes on exit
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $PYTHON_PID 2>/dev/null || true
  kill $SERVER_PID 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# Start flight data fetcher in background
echo "Starting flight data service..."
python3 fetch_flights.py &
PYTHON_PID=$!

# Give it a moment to create initial files
sleep 2

# Start HTTP server
echo "Starting HTTP server on http://localhost:8000"
cd web
python3 -m http.server 8000 &
SERVER_PID=$!
cd ..

echo ""
echo "✅ Skylight running!"
echo "   Open http://localhost:8000 in your browser"
echo "   Press Ctrl+C to stop"
echo ""

# Wait for either process to exit
wait
```

**Step 2: Make executable**

Run: `chmod +x dev.sh && ls -la dev.sh`
Expected: `-rwxr-xr-x` permissions

**Step 3: Commit**

```bash
git add dev.sh
git commit -m "feat: add development runner script"
```

---

## Task 10: Create Deployment Scripts

**Files:**
- Create: `deploy/skylight-data.service`
- Create: `deploy/skylight-display.service`
- Create: `deploy/setup-pi.sh`
- Create: `deploy.sh`

**Step 1: Create systemd service for data fetcher**

```ini
# deploy/skylight-data.service
[Unit]
Description=Skylight flight data fetcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/skylight
ExecStart=/usr/bin/python3 fetch_flights.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Step 2: Create systemd service for display**

```ini
# deploy/skylight-display.service
[Unit]
Description=Skylight kiosk display
After=skylight-data.service
Wants=skylight-data.service

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
ExecStartPre=/bin/sleep 3
ExecStart=/usr/bin/chromium-browser --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --incognito --disable-translate http://localhost:8000
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
```

**Step 3: Create Pi setup script**

```bash
#!/bin/bash
# deploy/setup-pi.sh - First-time Raspberry Pi setup for Skylight

set -e

echo "🛫 Setting up Skylight on Raspberry Pi..."

# Install dependencies
echo "Installing dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip chromium-browser

# Install Python packages
pip3 install requests

# Create web server service
echo "Creating HTTP server service..."
sudo tee /etc/systemd/system/skylight-http.service > /dev/null <<EOF
[Unit]
Description=Skylight HTTP server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/skylight/web
ExecStart=/usr/bin/python3 -m http.server 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Copy service files
echo "Installing systemd services..."
sudo cp /home/pi/skylight/deploy/skylight-data.service /etc/systemd/system/
sudo cp /home/pi/skylight/deploy/skylight-display.service /etc/systemd/system/

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable skylight-http
sudo systemctl enable skylight-data
sudo systemctl enable skylight-display

# Start services
sudo systemctl start skylight-http
sudo systemctl start skylight-data
sudo systemctl start skylight-display

echo ""
echo "✅ Skylight installed!"
echo "   Services will start automatically on boot."
echo ""
echo "   Useful commands:"
echo "   - sudo systemctl status skylight-data"
echo "   - sudo systemctl restart skylight-display"
echo "   - journalctl -u skylight-data -f"
```

**Step 4: Create deployment script**

```bash
#!/bin/bash
# deploy.sh - Deploy Skylight to Raspberry Pi

set -e

PI_HOST="${PI_HOST:-skylight.local}"
PI_USER="${PI_USER:-pi}"
PI_PATH="${PI_PATH:-/home/pi/skylight}"

echo "🛫 Deploying Skylight to ${PI_USER}@${PI_HOST}..."

# Sync files
rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'mockups' \
  --exclude '.DS_Store' \
  ./ "${PI_USER}@${PI_HOST}:${PI_PATH}/"

echo "Restarting services..."
ssh "${PI_USER}@${PI_HOST}" "sudo systemctl restart skylight-data skylight-http && sleep 2 && sudo systemctl restart skylight-display"

echo ""
echo "✅ Deployed!"
echo "   View logs: ssh ${PI_USER}@${PI_HOST} 'journalctl -u skylight-data -f'"
```

**Step 5: Make scripts executable and commit**

```bash
mkdir -p deploy
chmod +x deploy/setup-pi.sh
chmod +x deploy.sh
git add deploy/ deploy.sh
git commit -m "feat: add Pi deployment scripts and systemd services"
```

---

## Task 11: Test Full Stack Locally

**Step 1: Run development server**

Run: `./dev.sh`
Expected: Both Python service and HTTP server start

**Step 2: Verify in browser**

Open: `http://localhost:8000`
Expected:
- Dark background with subtle grid
- Planes appear and animate smoothly (if any in area)
- Trails follow planes
- Count updates in bottom left

**Step 3: Verify overlay behavior**

Stop the Python service (Ctrl+C in terminal, then restart just HTTP server).
Expected: "Reconnecting..." overlay appears

**Step 4: Document any issues found for refinement**

Note any visual issues (plane orientation, trail appearance) for next iteration.

---

## Task 12: Final Commit and Tag

**Step 1: Ensure all files are committed**

Run: `git status`
Expected: Working tree clean

**Step 2: Create summary commit if needed**

If any uncommitted changes:
```bash
git add -A
git commit -m "chore: cleanup and finalize web display implementation"
```

**Step 3: Tag the release**

```bash
git tag -a v2.0.0-web -m "Web-based flight display replacing pygame"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Configuration module | `config.py` |
| 2 | Flight data service | `fetch_flights.py` |
| 3 | HTML structure | `web/index.html` |
| 4 | CSS styles | `web/styles.css` |
| 5-8 | JavaScript app | `web/app.js` |
| 9 | Dev script | `dev.sh` |
| 10 | Deployment | `deploy/*`, `deploy.sh` |
| 11-12 | Testing & release | - |

**Known refinements for later:**
- Fix plane icon orientation (should face direction of travel)
- Longer trails with smoother gradient fade
- Fine-tune smoothing factor for Pi performance
