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
