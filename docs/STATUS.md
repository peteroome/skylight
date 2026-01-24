# Skylight Web Display - Current Status

## What's Working
- adsb.lol API fetching real flight data
- 8 planes displayed with correct colors and labels
- Global canvas for trails (single canvas, not per-plane)
- Velocity-based extrapolation between API updates
- Basic plane positioning on screen

## Known Issues (as of 2026-01-24)

### 1. Chaotic Trails
**Symptom:** Trails zigzag erratically, don't follow plane heading
**Likely causes:**
- Smoothing factor causing oscillation
- Trail points added too frequently during interpolation
- Position correction causing jumps when new API data arrives

### 2. Plane Icons Not Facing Direction of Travel
**Symptom:** Plane icons don't point in the direction they're moving
**Fix needed:** Adjust rotation offset (SVG icon may point wrong way by default)

### 3. Movement Feels Jerky
**Symptom:** Planes don't glide smoothly
**Likely cause:** Smoothing factor too aggressive, or extrapolation fighting with API corrections

## Debugging Approach

### Add Console Logging
In `web/app.js`, add logging to trace position updates:

```javascript
// In animate() function, add:
console.log(`[${id}] lat=${state.lat.toFixed(5)} lon=${state.lon.toFixed(5)} heading=${state.heading} vel=${state.velocity.toFixed(1)}`);
```

### Key Variables to Tune
| Variable | Current | Purpose |
|----------|---------|---------|
| `config.smoothingFactor` | 0.08 | How fast screen position catches up to target |
| `API_INTERVAL_S` | 5 | Seconds between API fetches |
| Trail add threshold | 1px | Minimum movement to add trail point |
| Trail max length | 500 | Points before oldest are removed |

## Files Structure
```
skylight/
├── config.py              # Python config (API, bounds, colors)
├── fetch_flights.py       # Python data service (adsb.lol)
├── web/
│   ├── index.html         # Page structure
│   ├── styles.css         # Visual styling
│   ├── app.js             # Browser rendering (MAIN LOGIC)
│   ├── config.json        # Generated from config.py
│   └── flights.json       # Current flight data
├── dev.sh                 # Local development script
└── deploy/                # Pi deployment files
```

## Next Steps
1. Add position logging to diagnose trail behavior
2. Remove smoothing temporarily to see raw movement
3. Fix plane icon rotation offset
4. Tune trail accumulation logic
