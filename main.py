import pygame
import sys
import os
import math
import requests
import platform
from datetime import datetime

# Configuration
BACKGROUND_COLOR = (0, 0, 0)

# Your location (73 Byne Rd, London SE26 5JG)
HOME_LAT = 51.4229712
HOME_LON = -0.0541772

# Bounding box for flight search
BBOX = {
    "min_lat": HOME_LAT - 0.5,
    "max_lat": HOME_LAT + 0.5,
    "min_lon": HOME_LON - 0.7,
    "max_lon": HOME_LON + 0.7,
}

# Visual settings
PLANE_COLOR = (70, 90, 140)
TRAIL_COLOR_BASE = (50, 70, 120)
TEXT_COLOR = (60, 80, 130)
TRAIL_WIDTH = 6
TRAIL_LENGTH = 300  # Number of trail points to keep
MAX_DISPLAY_PLANES = 15  # Only show this many planes
MAX_ALTITUDE = 12000  # Only show planes below this altitude (meters)
LABEL_COUNT = 8  # Only show labels for this many closest planes

# Country code mappings
COUNTRY_CODES = {
    "United Kingdom": "UK",
    "United States": "US",
    "Germany": "DE",
    "France": "FR",
    "Ireland": "IE",
    "Netherlands": "NL",
    "Spain": "ES",
    "Italy": "IT",
    "Switzerland": "CH",
    "Portugal": "PT",
    "Belgium": "BE",
    "Austria": "AT",
    "Poland": "PL",
    "Sweden": "SE",
    "Norway": "NO",
    "Denmark": "DK",
    "Finland": "FI",
    "Greece": "GR",
    "Turkey": "TR",
    "United Arab Emirates": "UAE",
    "Qatar": "QA",
    "Saudi Arabia": "SA",
    "China": "CN",
    "Japan": "JP",
    "Republic of Korea": "KR",
    "India": "IN",
    "Singapore": "SG",
    "Australia": "AU",
    "Canada": "CA",
    "Brazil": "BR",
    "Mexico": "MX",
    "Russia": "RU",
    "Israel": "IL",
    "South Africa": "ZA",
    "Morocco": "MA",
    "Egypt": "EG",
}

# Flight data
flights = {}
last_api_call = 0
API_INTERVAL = 10  # Seconds between API calls

# Screen dimensions (set at runtime)
screen_width = 800
screen_height = 450


def fetch_flights():
    """Fetch current flights from OpenSky Network"""
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": BBOX["min_lat"],
        "lomax": BBOX["max_lon"],
        "lamax": BBOX["max_lat"],
        "lomin": BBOX["min_lon"],
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("states", [])
    except Exception as e:
        print(f"API error: {e}")
    
    return []


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in meters"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return 6371000 * c


def calculate_sky_position(plane_lat, plane_lon, plane_alt):
    """
    Convert plane's lat/lon/alt to screen x/y position
    using flat map projection (planes fly straight across screen)
    """
    # Map lat/lon to screen coordinates based on bounding box
    # Longitude -> X (left to right)
    # Latitude -> Y (top to bottom, inverted because screen Y increases downward)

    lon_range = BBOX["max_lon"] - BBOX["min_lon"]
    lat_range = BBOX["max_lat"] - BBOX["min_lat"]

    # Normalize to 0-1 range
    norm_x = (plane_lon - BBOX["min_lon"]) / lon_range
    norm_y = (plane_lat - BBOX["min_lat"]) / lat_range

    # Convert to screen coordinates (invert Y so north is up)
    sx = norm_x * screen_width
    sy = (1 - norm_y) * screen_height

    # Calculate distance from home for sorting
    ground_distance = haversine_distance(HOME_LAT, HOME_LON, plane_lat, plane_lon)

    return sx, sy, ground_distance


def draw_fading_trail(screen, trail, base_color):
    """Draw a trail that fades from dim to solid"""
    if len(trail) < 2:
        return

    for i in range(len(trail) - 1):
        # Calculate fade factor (0.15 at start, 1 at end) - never fully invisible
        fade = 0.15 + 0.85 * (i / len(trail))

        # Interpolate color from dim to full base color
        color = (
            int(base_color[0] * fade),
            int(base_color[1] * fade),
            int(base_color[2] * fade),
        )

        # Draw line segment with varying thickness (thinner at tail)
        thickness = max(2, int(TRAIL_WIDTH * fade))

        start = trail[i]
        end = trail[i + 1]

        pygame.draw.line(screen, color, start, end, thickness)


def main():
    global flights, last_api_call, screen_width, screen_height

    # Track file modification time for auto-reload
    script_path = os.path.abspath(__file__)
    last_mtime = os.path.getmtime(script_path)

    pygame.init()
    
    on_pi = platform.machine().startswith('arm')
    
    if on_pi:
        screen_width, screen_height = 1280, 720
        screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    else:
        screen_width, screen_height = 800, 450
        screen = pygame.display.set_mode((screen_width, screen_height))
    
    pygame.display.set_caption("Skylight")
    pygame.mouse.set_visible(False)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 22)
    
    running = True
    last_frame_time = pygame.time.get_ticks()
    
    while running:
        current_time = pygame.time.get_ticks()
        dt = (current_time - last_frame_time) / 1000.0  # Delta time in seconds
        last_frame_time = current_time

        # Check for file changes and auto-reload
        try:
            current_mtime = os.path.getmtime(script_path)
            if current_mtime != last_mtime:
                print("File changed, reloading...")
                pygame.quit()
                os.execv(sys.executable, [sys.executable] + sys.argv)
        except OSError:
            pass

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
        
        # Fetch new flight data periodically
        if current_time / 1000 - last_api_call > API_INTERVAL:
            raw_flights = fetch_flights()
            last_api_call = current_time / 1000
            
            # Filter and process flights
            for state in raw_flights:
                if state[5] is None or state[6] is None:
                    continue
                
                icao = state[0]
                callsign = (state[1] or "").strip()
                origin_country = state[2] or ""
                lon = state[5]
                lat = state[6]
                alt = state[7] or 0
                velocity = state[9] or 0  # m/s
                heading = state[10] or 0  # degrees from north
                
                # Filter by altitude
                if alt > MAX_ALTITUDE:
                    continue
                
                screen_x, screen_y, distance = calculate_sky_position(lat, lon, alt)
                
                if icao not in flights:
                    # Create initial trail by projecting backwards from current position
                    # Project back ~60 seconds of flight time with ~100 sample points
                    initial_trail = []
                    if velocity > 0:
                        meters_per_degree_lat = 111000
                        meters_per_degree_lon = 111000 * math.cos(math.radians(lat))
                        heading_rad = math.radians(heading)

                        # Calculate how far plane travels per second in degrees
                        lat_speed = velocity * math.cos(heading_rad) / meters_per_degree_lat
                        lon_speed = velocity * math.sin(heading_rad) / meters_per_degree_lon

                        # Sample 100 points over 60 seconds of past travel
                        trail_duration = 60  # seconds
                        num_points = 100
                        for i in range(num_points):
                            t = (i / num_points) * trail_duration  # time in past (0 to 60 sec)
                            past_lat = lat - lat_speed * t
                            past_lon = lon - lon_speed * t
                            sx, sy, _ = calculate_sky_position(past_lat, past_lon, alt)
                            initial_trail.insert(0, (sx, sy))

                    flights[icao] = {
                        "trail": initial_trail,
                        "callsign": callsign,
                        "origin_country": origin_country,
                        "heading": heading,
                        "velocity": velocity,
                        "lat": lat,
                        "lon": lon,
                        "alt": alt,
                        "target_lat": lat,
                        "target_lon": lon,
                        "distance": distance,
                        "screen_x": screen_x,
                        "screen_y": screen_y,
                        "last_update": current_time,
                    }
                else:
                    # Store API position as target - we'll smoothly interpolate towards it
                    flights[icao]["target_lat"] = lat
                    flights[icao]["target_lon"] = lon
                    flights[icao]["heading"] = heading
                    flights[icao]["velocity"] = velocity
                    flights[icao]["alt"] = alt
                    flights[icao]["last_update"] = current_time

                flights[icao]["callsign"] = callsign
                flights[icao]["origin_country"] = origin_country
            
            # Remove stale flights (not seen in last 60 seconds)
            stale = [k for k, v in flights.items() if current_time - v["last_update"] > 60000]
            for k in stale:
                del flights[k]
            
            print(f"Tracking {len(flights)} flights")
        
        # Interpolate positions between API updates
        for icao, flight in flights.items():
            # Convert velocity from m/s to degrees per second
            # 1 degree latitude ≈ 111,000 meters
            # 1 degree longitude ≈ 111,000 * cos(latitude) meters
            meters_per_degree_lat = 111000
            meters_per_degree_lon = 111000 * math.cos(math.radians(flight["lat"]))

            heading_rad = math.radians(flight["heading"])

            # heading 0 = North (lat+), 90 = East (lon+), 180 = South (lat-), 270 = West (lon-)
            lat_speed = flight["velocity"] * math.cos(heading_rad) / meters_per_degree_lat
            lon_speed = flight["velocity"] * math.sin(heading_rad) / meters_per_degree_lon

            # Move plane based on its velocity
            flight["lat"] += lat_speed * dt
            flight["lon"] += lon_speed * dt

            # Also update target based on velocity so it stays ahead
            flight["target_lat"] += lat_speed * dt
            flight["target_lon"] += lon_speed * dt

            # Gently blend towards target position to correct drift without snapping
            # This prevents jarring jumps when API data arrives
            blend_rate = 0.5 * dt  # Blend 50% per second towards target
            flight["lat"] += (flight["target_lat"] - flight["lat"]) * blend_rate
            flight["lon"] += (flight["target_lon"] - flight["lon"]) * blend_rate

            # Recalculate screen position
            sx, sy, dist = calculate_sky_position(flight["lat"], flight["lon"], flight["alt"])
            flight["screen_x"] = sx
            flight["screen_y"] = sy
            flight["distance"] = dist

            # Add to trail only if position changed enough (at least 1 pixel)
            # This prevents trail points stacking when movement is sub-pixel
            if len(flight["trail"]) == 0:
                flight["trail"].append((sx, sy))
            else:
                last_x, last_y = flight["trail"][-1]
                dx = sx - last_x
                dy = sy - last_y
                if dx * dx + dy * dy >= 1:  # At least 1 pixel movement
                    flight["trail"].append((sx, sy))
                    flight["trail"] = flight["trail"][-TRAIL_LENGTH:]
        
        # Sort flights by distance for display priority
        sorted_flights = sorted(flights.items(), key=lambda x: x[1]["distance"])
        display_flights = sorted_flights[:MAX_DISPLAY_PLANES]
        
        # Clear screen
        screen.fill(BACKGROUND_COLOR)
        
        # Draw flights (furthest first so closest are on top)
        for i, (icao, flight) in enumerate(reversed(display_flights)):
            trail = flight["trail"]
            
            if len(trail) < 2:
                continue
            
            # Draw fading trail
            draw_fading_trail(screen, trail, TRAIL_COLOR_BASE)
            
            # Draw plane dot at current position
            current_pos = (int(flight["screen_x"]), int(flight["screen_y"]))
            pygame.draw.circle(screen, PLANE_COLOR, current_pos, 5)
            
            # Only show labels for closest planes
            rank = MAX_DISPLAY_PLANES - 1 - i
            if rank < LABEL_COUNT:
                # Use callsign if available, otherwise use ICAO code
                display_name = flight["callsign"] if flight["callsign"] else icao.upper()

                # Render callsign/ICAO
                callsign_label = font.render(display_name, True, TEXT_COLOR)
                callsign_x = current_pos[0] - callsign_label.get_width() // 2
                callsign_y = current_pos[1] + 10
                screen.blit(callsign_label, (callsign_x, callsign_y))

                # Render country code below callsign
                if flight["origin_country"]:
                    country_code = COUNTRY_CODES.get(flight["origin_country"], flight["origin_country"][:3].upper())
                else:
                    country_code = "?"
                country_label = font.render(f"({country_code})", True, TEXT_COLOR)
                country_x = current_pos[0] - country_label.get_width() // 2
                country_y = callsign_y + 16
                screen.blit(country_label, (country_x, country_y))
        
        pygame.display.flip()
        clock.tick(30)
    
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()