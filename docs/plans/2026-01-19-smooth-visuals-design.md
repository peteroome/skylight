# Smooth Visuals Design

## Problem

The flight tracker on a projector has three visual issues:

1. **Micro-stuttering** - API calls block the main rendering thread
2. **Choppy frame rate** - 30 FPS feels jerky on projector
3. **Position jumps** - Planes snap to new positions when API data arrives

Additionally, trails are too thin (1px) to see clearly on a projector for a 4-year-old.

## Solution

### 1. Threaded API Calls

Move network calls to a background thread so rendering never blocks.

```
Main Thread                    Background Thread
-----------                    -----------------
render frame                   fetch_flights() starts
render frame                   ...waiting for network...
render frame                   ...got response...
render frame                   places results in queue
processes queue <------------
render frame
```

**Implementation:**
- `threading.Thread` with `daemon=True`
- `queue.Queue` for thread-safe data passing
- Background thread sleeps `API_INTERVAL` between calls
- Main thread uses `queue.get_nowait()` (non-blocking)

### 2. Smooth Position Blending

When new API data arrives, blend from predicted position to actual over 1 second.

**New flight state fields:**
- `blend_from_lat`, `blend_from_lon` - position when blend started
- `blend_progress` - 0.0 to 1.0

**Each frame during blending:**
```python
blend_progress += dt / BLEND_DURATION  # BLEND_DURATION = 1.0s
t = min(blend_progress, 1.0)
render_lat = blend_from_lat + (lat - blend_from_lat) * t
render_lon = blend_from_lon + (lon - blend_from_lon) * t
```

After blend completes, resume velocity-based extrapolation.

### 3. FPS Increase

Change `TARGET_FPS` from 30 to 60. Pi Zero 2W handles this easily.

### 4. Trail Optimization

Replace list with `collections.deque`:

```python
# Before - creates garbage
if len(trail) > TRAIL_LENGTH:
    f["trail"] = trail[-TRAIL_LENGTH:]

# After - no allocation
from collections import deque
trail = deque(maxlen=TRAIL_LENGTH)
trail.append((sx, sy))
```

### 5. Chunky Trails

Change trail rendering for projector visibility:

- Line width: 1px → 6px
- Use `pygame.draw.line(..., width=6)` instead of `aaline`
- Keep fade effect (older points dimmer)

## Changes Summary

| File | Change |
|------|--------|
| main.py | Add threading, queue imports |
| main.py | Add deque import |
| main.py | New constants: BLEND_DURATION, TRAIL_WIDTH |
| main.py | TARGET_FPS: 30 → 60 |
| main.py | New function: api_worker() - background thread |
| main.py | Update flight state to include blend fields |
| main.py | Update position logic for blending |
| main.py | Update draw_trail() for thick lines |
| main.py | Use deque for trails |

## Testing

1. Run on desktop - verify no freezes during API calls
2. Check planes blend smoothly when new data arrives
3. Verify trails are visibly thicker
4. Deploy to Pi Zero 2W and test on projector
