import pygame
import pygame.gfxdraw
import sys
import os
import math
import requests
import platform
import threading
import queue
from collections import deque

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
TARGET_FPS = 60
API_INTERVAL = 15
BLEND_DURATION = 1.0  # Seconds to blend from predicted to actual position
TRAIL_WIDTH = 15  # Chunky trails for projector visibility
PLANE_SIZE = 14  # Size of plane icon

# Flight data
flights = {}
flight_queue = queue.Queue()  # Thread-safe queue for API results

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


def api_worker():
    """Background thread that fetches flight data periodically"""
    import time
    while True:
        states = fetch_flights()
        if states:
            flight_queue.put(states)
        time.sleep(API_INTERVAL)


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
    """Draw thick trail that fades from dim to bright"""
    n = len(trail)
    if n < 2:
        return

    # Convert deque to list for indexing
    trail_list = list(trail)
    r, g, b = TRAIL_COLOR
    for i in range(n - 1):
        fade = 0.2 + 0.8 * i / n
        color = (int(r * fade), int(g * fade), int(b * fade))
        pygame.draw.line(surface, color, trail_list[i], trail_list[i + 1], TRAIL_WIDTH)


def draw_plane(surface, x, y, heading, color, size):
    """Draw a cute plane icon rotated to match heading"""
    # Heading: 0=North, 90=East, 180=South, 270=West
    # Convert to radians, adjust so 0 points up
    angle = math.radians(heading)

    # Plane shape points (pointing up when angle=0)
    # Body, wings, tail - simple cartoon plane
    s = size
    points = [
        (0, -s * 1.5),      # Nose
        (s * 0.4, -s * 0.3),  # Right front
        (s * 1.5, s * 0.2),   # Right wing tip
        (s * 0.4, s * 0.3),   # Right wing back
        (s * 0.3, s * 1.0),   # Right tail
        (s * 0.8, s * 1.5),   # Right tail tip
        (0, s * 1.1),         # Tail center
        (-s * 0.8, s * 1.5),  # Left tail tip
        (-s * 0.3, s * 1.0),  # Left tail
        (-s * 0.4, s * 0.3),  # Left wing back
        (-s * 1.5, s * 0.2),  # Left wing tip
        (-s * 0.4, -s * 0.3), # Left front
    ]

    # Rotate and translate points
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    rotated = []
    for px, py in points:
        rx = px * cos_a - py * sin_a + x
        ry = px * sin_a + py * cos_a + y
        rotated.append((rx, ry))

    # Draw filled plane
    pygame.draw.polygon(surface, color, rotated)
    # Draw outline for definition
    pygame.draw.polygon(surface, (min(color[0] + 40, 255), min(color[1] + 40, 255), min(color[2] + 40, 255)), rotated, 2)


def create_initial_trail(lat, lon, alt, velocity, heading):
    """Project trail backwards based on velocity/heading"""
    trail = deque(maxlen=TRAIL_LENGTH)
    if velocity <= 0:
        return trail

    cos_lat = math.cos(math.radians(lat))
    heading_rad = math.radians(heading)
    lat_speed = velocity * math.cos(heading_rad) / 111000
    lon_speed = velocity * math.sin(heading_rad) / (111000 * cos_lat)

    # Build trail from oldest to newest
    for i in range(TRAIL_LENGTH, 0, -1):
        t = i * 180 / TRAIL_LENGTH  # 0 to 180 seconds back
        trail.append(lat_lon_to_screen(lat - lat_speed * t, lon - lon_speed * t))
    return trail


def main():
    global flights, screen_width, screen_height

    pygame.init()
    on_pi = platform.machine().startswith('arm')

    if on_pi:
        screen_width, screen_height = 1280, 720
        screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    else:
        screen_width, screen_height = 1280, 720
        screen = pygame.display.set_mode((screen_width, screen_height))

    # Start background API thread
    api_thread = threading.Thread(target=api_worker, daemon=True)
    api_thread.start()

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

        # Process flight data from background thread (non-blocking)
        try:
            while True:
                states = flight_queue.get_nowait()
                for state in states:
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
                            "render_lat": lat, "render_lon": lon,  # Current rendered position
                            "velocity": velocity, "heading": heading,
                            "callsign": callsign, "country": country,
                            "last_seen": now,
                            "blend_progress": 1.0  # No blending needed for new planes
                        }
                    else:
                        f = flights[icao]
                        # Check if new position is ahead of current position in heading direction
                        # If behind, snap instead of blend to avoid sliding backwards
                        heading_rad = math.radians(f["heading"])
                        dx = lat - f["render_lat"]  # Delta in lat (roughly north)
                        dy = lon - f["render_lon"]  # Delta in lon (roughly east)
                        # Project onto heading direction (positive = ahead, negative = behind)
                        forward = dx * math.cos(heading_rad) + dy * math.sin(heading_rad)

                        if forward >= 0:
                            # New position is ahead - blend smoothly
                            f["blend_from_lat"] = f["render_lat"]
                            f["blend_from_lon"] = f["render_lon"]
                            f["blend_progress"] = 0.0
                        else:
                            # New position is behind - snap to avoid backwards sliding
                            f["render_lat"] = lat
                            f["render_lon"] = lon
                            f["blend_progress"] = 1.0

                        # Update target position
                        f["lat"], f["lon"], f["alt"] = lat, lon, alt
                        f["velocity"], f["heading"] = velocity, heading
                        f["callsign"], f["country"] = callsign, country
                        f["last_seen"] = now

                # Remove stale flights
                flights = {k: v for k, v in flights.items() if now - v["last_seen"] < 60000}
                print(f"Tracking {len(flights)} flights")
        except queue.Empty:
            pass  # No new data, continue rendering

        # Update positions
        for f in flights.values():
            # Extrapolate target position based on velocity
            if f["velocity"] > 0:
                cos_lat = math.cos(math.radians(f["lat"]))
                heading_rad = math.radians(f["heading"])
                f["lat"] += f["velocity"] * math.cos(heading_rad) / 111000 * dt
                f["lon"] += f["velocity"] * math.sin(heading_rad) / (111000 * cos_lat) * dt

            # Handle position blending
            if f["blend_progress"] < 1.0:
                f["blend_progress"] += dt / BLEND_DURATION
                t = min(f["blend_progress"], 1.0)
                # Smooth easing (ease-out)
                t = 1 - (1 - t) ** 2
                f["render_lat"] = f["blend_from_lat"] + (f["lat"] - f["blend_from_lat"]) * t
                f["render_lon"] = f["blend_from_lon"] + (f["lon"] - f["blend_from_lon"]) * t
            else:
                f["render_lat"] = f["lat"]
                f["render_lon"] = f["lon"]

            sx, sy = lat_lon_to_screen(f["render_lat"], f["render_lon"])
            f["sx"], f["sy"] = sx, sy

            # Add to trail if moved enough (deque auto-limits size)
            trail = f["trail"]
            if not trail or (sx - trail[-1][0])**2 + (sy - trail[-1][1])**2 >= 1:
                trail.append((sx, sy))

        # Sort by distance, take closest
        sorted_flights = sorted(flights.items(), key=lambda x: distance_from_home(x[1]["lat"], x[1]["lon"]))
        visible = sorted_flights[:MAX_PLANES]

        # Draw
        screen.fill(BACKGROUND_COLOR)

        for icao, f in reversed(visible):
            if len(f["trail"]) >= 2:
                draw_trail(screen, f["trail"])

            cx, cy = int(f["sx"]), int(f["sy"])
            draw_plane(screen, cx, cy, f["heading"], PLANE_COLOR, PLANE_SIZE)

            # Labels (offset below the plane)
            name = f["callsign"] or icao.upper()
            label1 = font.render(name, True, TEXT_COLOR)
            label2 = font.render(f"({f['country'] or 'Unknown'})", True, TEXT_COLOR)
            screen.blit(label1, (cx - label1.get_width() // 2, cy + PLANE_SIZE * 2))
            screen.blit(label2, (cx - label2.get_width() // 2, cy + PLANE_SIZE * 2 + 16))

        pygame.display.flip()
        clock.tick(TARGET_FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()