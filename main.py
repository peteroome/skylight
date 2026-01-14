import pygame
import pygame.gfxdraw
import sys
import os
import math
import requests
import platform

# Configuration
BACKGROUND_COLOR = (0, 0, 0)

# Your location (73 Byne Rd, London SE26 5JG)
HOME_LAT = 51.4229712
HOME_LON = -0.0541772

# Bounding box for flight search (~26km x 48km area)
LAT_SPAN = 0.12
LON_SPAN = 0.34
MIN_LAT = HOME_LAT - LAT_SPAN
MAX_LAT = HOME_LAT + LAT_SPAN
MIN_LON = HOME_LON - LON_SPAN
MAX_LON = HOME_LON + LON_SPAN
LAT_RANGE = MAX_LAT - MIN_LAT
LON_RANGE = MAX_LON - MIN_LON

# Visual settings
PLANE_COLOR = (90, 120, 180)
TRAIL_COLOR = (80, 110, 170)
TEXT_COLOR = (70, 100, 160)

# Performance settings
MAX_ALTITUDE = 12000
TRAIL_LENGTH = 500
MAX_PLANES = 8
TARGET_FPS = 30
API_INTERVAL = 15

# Flight data
flights = {}
last_api_call = 0

# Screen dimensions (set at runtime)
screen_width = 800
screen_height = 450


def fetch_flights():
    """Fetch current flights from OpenSky Network"""
    try:
        response = requests.get(
            "https://opensky-network.org/api/states/all",
            params={"lamin": MIN_LAT, "lamax": MAX_LAT, "lomin": MIN_LON, "lomax": MAX_LON},
            timeout=10
        )
        if response.status_code == 200:
            states = response.json().get("states")
            return states if states else []
    except Exception as e:
        print(f"API error: {e}")
    return []


def lat_lon_to_screen(lat, lon):
    """Convert lat/lon to screen coordinates"""
    x = (lon - MIN_LON) / LON_RANGE * screen_width
    y = (1 - (lat - MIN_LAT) / LAT_RANGE) * screen_height
    return x, y


def distance_from_home(lat, lon):
    """Simple distance calculation for sorting (squared, no sqrt needed)"""
    dlat = lat - HOME_LAT
    dlon = lon - HOME_LON
    return dlat * dlat + dlon * dlon


def draw_trail(surface, trail):
    """Draw anti-aliased trail that fades from dim to bright"""
    n = len(trail)
    if n < 2:
        return

    r, g, b = TRAIL_COLOR
    for i in range(n - 1):
        fade = 0.2 + 0.8 * i / n
        color = (int(r * fade), int(g * fade), int(b * fade))
        pygame.draw.aaline(surface, color, trail[i], trail[i + 1])


def create_initial_trail(lat, lon, alt, velocity, heading):
    """Project trail backwards based on velocity/heading"""
    if velocity <= 0:
        return []

    cos_lat = math.cos(math.radians(lat))
    heading_rad = math.radians(heading)
    lat_speed = velocity * math.cos(heading_rad) / 111000
    lon_speed = velocity * math.sin(heading_rad) / (111000 * cos_lat)

    # Build trail from oldest to newest (avoids slow insert(0))
    trail = []
    for i in range(TRAIL_LENGTH, 0, -1):
        t = i * 180 / TRAIL_LENGTH  # 0 to 180 seconds back
        trail.append(lat_lon_to_screen(lat - lat_speed * t, lon - lon_speed * t))
    return trail


def main():
    global flights, last_api_call, screen_width, screen_height

    pygame.init()
    on_pi = platform.machine().startswith('arm')

    if on_pi:
        screen_width, screen_height = 1280, 720
        screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    else:
        screen_width, screen_height = 800, 450
        screen = pygame.display.set_mode((screen_width, screen_height))

    # Auto-reload on file save (dev only)
    script_path = os.path.abspath(__file__) if not on_pi else None
    last_mtime = os.path.getmtime(script_path) if script_path else 0

    pygame.display.set_caption("Skylight")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 22)

    running = True
    prev_time = pygame.time.get_ticks()

    while running:
        now = pygame.time.get_ticks()
        dt = (now - prev_time) / 1000.0
        prev_time = now

        # Auto-reload check (dev only)
        if script_path:
            try:
                mtime = os.path.getmtime(script_path)
                if mtime != last_mtime:
                    pygame.quit()
                    os.execv(sys.executable, [sys.executable] + sys.argv)
            except OSError:
                pass

        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False

        # Fetch flight data periodically
        if now / 1000 - last_api_call > API_INTERVAL:
            last_api_call = now / 1000

            for state in fetch_flights():
                if state[5] is None or state[6] is None:
                    continue

                icao, callsign, country = state[0], (state[1] or "").strip(), state[2] or ""
                lon, lat, alt = state[5], state[6], state[7] or 0
                velocity, heading = state[9] or 0, state[10] or 0

                if alt > MAX_ALTITUDE:
                    continue

                if icao not in flights:
                    flights[icao] = {
                        "trail": create_initial_trail(lat, lon, alt, velocity, heading),
                        "lat": lat, "lon": lon, "alt": alt,
                        "velocity": velocity, "heading": heading,
                        "callsign": callsign, "country": country,
                        "last_seen": now
                    }
                else:
                    f = flights[icao]
                    f["lat"], f["lon"], f["alt"] = lat, lon, alt
                    f["velocity"], f["heading"] = velocity, heading
                    f["callsign"], f["country"] = callsign, country
                    f["last_seen"] = now

            # Remove stale flights
            flights = {k: v for k, v in flights.items() if now - v["last_seen"] < 60000}
            print(f"Tracking {len(flights)} flights")

        # Update positions
        for f in flights.values():
            if f["velocity"] > 0:
                cos_lat = math.cos(math.radians(f["lat"]))
                heading_rad = math.radians(f["heading"])
                f["lat"] += f["velocity"] * math.cos(heading_rad) / 111000 * dt
                f["lon"] += f["velocity"] * math.sin(heading_rad) / (111000 * cos_lat) * dt

            sx, sy = lat_lon_to_screen(f["lat"], f["lon"])
            f["sx"], f["sy"] = sx, sy

            # Add to trail if moved enough
            trail = f["trail"]
            if not trail or (sx - trail[-1][0])**2 + (sy - trail[-1][1])**2 >= 1:
                trail.append((sx, sy))
                if len(trail) > TRAIL_LENGTH:
                    f["trail"] = trail[-TRAIL_LENGTH:]

        # Sort by distance, take closest
        sorted_flights = sorted(flights.items(), key=lambda x: distance_from_home(x[1]["lat"], x[1]["lon"]))
        visible = sorted_flights[:MAX_PLANES]

        # Draw
        screen.fill(BACKGROUND_COLOR)

        for icao, f in reversed(visible):
            if len(f["trail"]) >= 2:
                draw_trail(screen, f["trail"])

            cx, cy = int(f["sx"]), int(f["sy"])
            pygame.gfxdraw.aacircle(screen, cx, cy, 5, PLANE_COLOR)
            pygame.gfxdraw.filled_circle(screen, cx, cy, 5, PLANE_COLOR)

            # Labels
            name = f["callsign"] or icao.upper()
            label1 = font.render(name, True, TEXT_COLOR)
            label2 = font.render(f"({f['country'] or 'Unknown'})", True, TEXT_COLOR)
            screen.blit(label1, (cx - label1.get_width() // 2, cy + 10))
            screen.blit(label2, (cx - label2.get_width() // 2, cy + 26))

        pygame.display.flip()
        clock.tick(TARGET_FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()