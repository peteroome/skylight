# Skylight

A real-time flight tracker visualization for a Raspberry Pi, displaying planes flying overhead like a digital skylight.

## Features

- Real-time flight data from [OpenSky Network](https://opensky-network.org/)
- Smooth anti-aliased trails showing flight paths
- Flat map projection centered on your location
- Labels showing callsign and country of origin
- Auto-reload on file save during development (desktop only)
- Optimized for Raspberry Pi (tested on original Model B)

## Requirements

- Python 3
- pygame
- requests

```bash
pip install pygame requests
```

## Configuration

Edit the coordinates in `main.py` to set your location:

```python
HOME_LAT = 51.4229712  # Your latitude
HOME_LON = -0.0541772  # Your longitude
```

Adjust the viewing area with `LAT_SPAN` and `LON_SPAN` (currently ~26km × 48km).

## Usage

```bash
python main.py
```

- **Desktop**: Opens in an 800×450 window with auto-reload on file save
- **Raspberry Pi**: Runs fullscreen at 1280×720

Press `ESC` to exit.

## Performance Settings

Tunable in `main.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `MAX_ALTITUDE` | 12000m | Only show planes below this altitude |
| `TRAIL_LENGTH` | 500 | Number of trail points per plane |
| `MAX_PLANES` | 8 | Maximum planes to display |
| `TARGET_FPS` | 30 | Frame rate |
| `API_INTERVAL` | 15s | Seconds between API calls |

## API

Uses the free OpenSky Network API (no authentication required). Rate limits apply.

## License

Apache 2.0
