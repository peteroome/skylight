// web/app.js - Smooth trajectory-based plane animation

// ─── Performance Configuration ────────────────────
// Set to false to disable trails for better performance on low-end devices
const ENABLE_TRAILS = true;
const ENABLE_CURVES = true; // Set to false for straight paths only

// ─── State ────────────────────────────────────────
let config = null;
let planes = new Map(); // id -> plane state
let isConnected = false;

// ─── DOM Elements ─────────────────────────────────
const planesContainer = document.getElementById('planes');
const countEl = document.getElementById('count');
const overlayEl = document.getElementById('overlay');
const overlayTextEl = document.getElementById('overlay-text');
const trailsCanvas = document.getElementById('trails');
const trailsCtx = trailsCanvas.getContext('2d');

// ─── Configuration ────────────────────────────────
async function loadConfig() {
  try {
    const response = await fetch('config.json');
    config = await response.json();
    console.log('Config loaded:', config);
    return true;
  } catch (e) {
    console.error('Failed to load config:', e);
    config = {
      pollIntervalMs: 1500,
      home: { lat: 51.4229712, lon: -0.0541772 },
      bounds: {
        minLat: 51.1729712,
        maxLat: 51.6729712,
        minLon: -0.5041772,
        maxLon: 0.3958228,
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

function screenToLatLon(x, y) {
  const { minLat, maxLat, minLon, maxLon } = config.bounds;
  const lon = (x / window.innerWidth) * (maxLon - minLon) + minLon;
  const lat = (1 - y / window.innerHeight) * (maxLat - minLat) + minLat;
  return { lat, lon };
}

// ─── Calculate Exit Point ─────────────────────────
// Project from current position along heading until we hit a screen edge
function calculateExitPoint(startLat, startLon, headingDeg) {
  const { minLat, maxLat, minLon, maxLon } = config.bounds;

  // Convert heading to radians (0° = North, 90° = East)
  const headingRad = (headingDeg * Math.PI) / 180;

  // Direction vector (in lat/lon space)
  const dLat = Math.cos(headingRad);
  const dLon = Math.sin(headingRad);

  // Find intersection with each edge
  let minT = Infinity;

  // Top edge (maxLat)
  if (dLat > 0) {
    const t = (maxLat - startLat) / dLat;
    if (t > 0 && t < minT) minT = t;
  }
  // Bottom edge (minLat)
  if (dLat < 0) {
    const t = (minLat - startLat) / dLat;
    if (t > 0 && t < minT) minT = t;
  }
  // Right edge (maxLon)
  if (dLon > 0) {
    const t = (maxLon - startLon) / dLon;
    if (t > 0 && t < minT) minT = t;
  }
  // Left edge (minLon)
  if (dLon < 0) {
    const t = (minLon - startLon) / dLon;
    if (t > 0 && t < minT) minT = t;
  }

  // Calculate exit point
  const exitLat = startLat + dLat * minT;
  const exitLon = startLon + dLon * minT;

  // Calculate distance in meters (approximate)
  const distanceDeg = Math.sqrt(
    Math.pow(exitLat - startLat, 2) +
    Math.pow((exitLon - startLon) * Math.cos(startLat * Math.PI / 180), 2)
  );
  const distanceMeters = distanceDeg * 111000;

  return { lat: exitLat, lon: exitLon, distanceMeters };
}

// ─── Easing Function ──────────────────────────────
// Smooth ease-in-out for natural movement
function easeInOutSine(t) {
  return -(Math.cos(Math.PI * t) - 1) / 2;
}

// Linear for constant speed (planes don't accelerate mid-flight)
function linear(t) {
  return t;
}

// ─── Bezier Curve Interpolation ───────────────────
// Quadratic bezier: P = (1-t)²P0 + 2(1-t)tP1 + t²P2
function quadraticBezier(t, p0, p1, p2) {
  const mt = 1 - t;
  return mt * mt * p0 + 2 * mt * t * p1 + t * t * p2;
}

// Generate a control point for curved path
// Returns null for straight paths, or {lat, lon} for curved
function generateCurveControl(startLat, startLon, endLat, endLon, heading) {
  // Skip curves if disabled for performance
  if (!ENABLE_CURVES) return null;

  // 60% of planes get curves
  if (Math.random() > 0.6) return null;

  // Calculate midpoint
  const midLat = (startLat + endLat) / 2;
  const midLon = (startLon + endLon) / 2;

  // Calculate perpendicular direction (90° from heading)
  const perpRad = ((heading + 90) * Math.PI) / 180;

  // Random offset magnitude (as fraction of journey distance)
  // Positive or negative for left/right curves
  const journeyDist = Math.sqrt(
    Math.pow(endLat - startLat, 2) +
    Math.pow(endLon - startLon, 2)
  );
  const offsetMagnitude = journeyDist * (0.1 + Math.random() * 0.15); // 10-25% of journey
  const offsetSign = Math.random() > 0.5 ? 1 : -1;

  // Apply offset perpendicular to flight path
  const controlLat = midLat + Math.cos(perpRad) * offsetMagnitude * offsetSign;
  const controlLon = midLon + Math.sin(perpRad) * offsetMagnitude * offsetSign;

  return { lat: controlLat, lon: controlLon };
}

// ─── Hex to RGB Helper ────────────────────────────
function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  } : { r: 255, g: 255, b: 255 };
}

// ─── Draw Trails ──────────────────────────────────
function drawTrails() {
  // Clear canvas
  trailsCtx.clearRect(0, 0, trailsCanvas.width, trailsCanvas.height);

  for (const state of planes.values()) {
    if (!state.screenPos) continue;

    const rgb = hexToRgb(state.color);
    const progress = state.progress || 0;

    // Trail starts fading from the back after 60% progress
    // fadeProgress: 0 at 60%, 1 at 100%
    const fadeProgress = progress > 0.6 ? (progress - 0.6) / 0.4 : 0;

    // Calculate where the visible trail starts (fades from the back)
    const trailStartProgress = fadeProgress * progress;

    // Get trail start and end positions
    let trailStartLat, trailStartLon;
    if (state.curveControl) {
      trailStartLat = quadraticBezier(trailStartProgress, state.startLat, state.curveControl.lat, state.endLat);
      trailStartLon = quadraticBezier(trailStartProgress, state.startLon, state.curveControl.lon, state.endLon);
    } else {
      trailStartLat = state.startLat + (state.endLat - state.startLat) * trailStartProgress;
      trailStartLon = state.startLon + (state.endLon - state.startLon) * trailStartProgress;
    }
    const trailStart = latLonToScreen(trailStartLat, trailStartLon);

    // Draw smooth bezier curve or straight line
    trailsCtx.beginPath();
    trailsCtx.moveTo(trailStart.x, trailStart.y);

    if (state.curveControl) {
      // For bezier, use minimal segments for Pi Zero performance
      const segments = 4;
      for (let i = 1; i <= segments; i++) {
        const t = trailStartProgress + (progress - trailStartProgress) * (i / segments);
        const lat = quadraticBezier(t, state.startLat, state.curveControl.lat, state.endLat);
        const lon = quadraticBezier(t, state.startLon, state.curveControl.lon, state.endLon);
        const pos = latLonToScreen(lat, lon);
        trailsCtx.lineTo(pos.x, pos.y);
      }
    } else {
      // Straight line
      trailsCtx.lineTo(state.screenPos.x, state.screenPos.y);
    }

    // Create gradient from trail start (faded) to plane (more visible but still subtle)
    const gradient = trailsCtx.createLinearGradient(
      trailStart.x, trailStart.y,
      state.screenPos.x, state.screenPos.y
    );
    gradient.addColorStop(0, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0)`);
    gradient.addColorStop(0.3, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.15)`);
    gradient.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.4)`);

    trailsCtx.strokeStyle = gradient;
    trailsCtx.lineWidth = 4;
    trailsCtx.lineCap = 'butt'; // Faster than 'round'
    trailsCtx.stroke();
  }
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

  const icon = document.createElement('div');
  icon.className = 'plane-icon';
  icon.innerHTML = PLANE_SVG;
  el.appendChild(icon);

  const label = document.createElement('div');
  label.className = 'plane-label';
  el.appendChild(label);

  planesContainer.appendChild(el);
  return el;
}

// ─── Update Plane Element ─────────────────────────
function updatePlaneElement(el, state) {
  const { x, y } = state.screenPos;

  el.style.transform = `translate(${x - 24}px, ${y - 24}px)`;

  const icon = el.querySelector('.plane-icon');
  icon.style.transform = `rotate(${state.heading}deg)`;

  const label = el.querySelector('.plane-label');
  const displayName = state.callsign || state.id.slice(-6).toUpperCase();
  label.textContent = `${displayName} - ${state.country}`;
}

// ─── Remove Plane Element ─────────────────────────
function removePlaneElement(id) {
  const el = document.getElementById(`plane-${id}`);
  if (el) el.remove();
}

// ─── Animation Loop ───────────────────────────────
let lastAnimateTime = 0;
const TARGET_FPS = 30; // Limit to 15fps for Pi Zero performance
const FRAME_INTERVAL = 1000 / TARGET_FPS;

function animate(currentTime) {
  // Throttle frame rate for Pi performance
  const elapsed = currentTime - lastAnimateTime;
  if (elapsed < FRAME_INTERVAL) {
    requestAnimationFrame(animate);
    return;
  }
  lastAnimateTime = currentTime - (elapsed % FRAME_INTERVAL);

  const toRemove = [];

  for (const [id, state] of planes) {
    // Calculate progress (0 to 1)
    const elapsed = currentTime - state.startTime;
    const progress = Math.min(elapsed / state.duration, 1);
    state.progress = progress; // Store for trail drawing

    // Apply easing
    const easedProgress = linear(progress);

    // Interpolate position (curved or straight)
    if (state.curveControl) {
      // Quadratic bezier curve
      state.lat = quadraticBezier(easedProgress, state.startLat, state.curveControl.lat, state.endLat);
      state.lon = quadraticBezier(easedProgress, state.startLon, state.curveControl.lon, state.endLon);

      // Calculate tangent direction for heading (derivative of bezier)
      const dt = 0.01;
      const nextT = Math.min(easedProgress + dt, 1);
      const nextLat = quadraticBezier(nextT, state.startLat, state.curveControl.lat, state.endLat);
      const nextLon = quadraticBezier(nextT, state.startLon, state.curveControl.lon, state.endLon);
      state.heading = Math.atan2(nextLon - state.lon, nextLat - state.lat) * 180 / Math.PI;
    } else {
      // Straight line
      state.lat = state.startLat + (state.endLat - state.startLat) * easedProgress;
      state.lon = state.startLon + (state.endLon - state.startLon) * easedProgress;
    }
    state.screenPos = latLonToScreen(state.lat, state.lon);

    // Store trail points for curved paths (sample every ~2% progress)
    if (state.trailPoints.length === 0 || progress - state.lastTrailProgress > 0.02) {
      state.trailPoints.push({ x: state.screenPos.x, y: state.screenPos.y });
      state.lastTrailProgress = progress;
      // Keep trail reasonable length
      if (state.trailPoints.length > 50) state.trailPoints.shift();
    }

    // Ensure start screen position is set (for trails)
    if (!state.startScreenPos) {
      state.startScreenPos = latLonToScreen(state.startLat, state.startLon);
    }

    // Update DOM
    let el = document.getElementById(`plane-${id}`);
    if (!el) {
      el = createPlaneElement(id, state.color);
    }
    updatePlaneElement(el, state);

    // Mark for removal if journey complete
    if (progress >= 1) {
      toRemove.push(id);
    }
  }

  // Remove completed planes
  for (const id of toRemove) {
    removePlaneElement(id);
    planes.delete(id);
  }

  // Update count
  updateCount(planes.size);

  // Draw trails (if enabled)
  if (ENABLE_TRAILS) drawTrails();

  requestAnimationFrame(animate);
}

// ─── Fetch Flight Data ────────────────────────────
async function fetchFlightData() {
  try {
    const response = await fetch('flights.json?' + Date.now());
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();

    if (data.status === 'error') {
      if (isConnected) {
        showOverlay('Connection lost. Reconnecting...');
        isConnected = false;
      }
      return;
    }

    if (!isConnected) {
      hideOverlay();
      isConnected = true;
    }

    // Process planes
    for (const planeData of data.planes) {
      // Skip if we're already tracking this plane
      if (planes.has(planeData.id)) {
        // Optionally update callsign/country if they changed
        const state = planes.get(planeData.id);
        state.callsign = planeData.callsign;
        state.country = planeData.country;
        continue;
      }

      // New plane - calculate trajectory
      const startLat = planeData.position.lat;
      const startLon = planeData.position.lon;
      const heading = planeData.heading;
      const velocityMps = planeData.velocity_mps || 200; // Default ~400 knots

      // Calculate where this plane will exit the screen
      const exit = calculateExitPoint(startLat, startLon, heading);

      // Calculate duration based on distance and speed
      // Speed multiplier to make planes move faster (2 = twice as fast)
      const speedMultiplier = 3;
      const durationMs = (exit.distanceMeters / velocityMps / speedMultiplier) * 1000;

      // Generate curve control point (may be null for straight paths)
      const curveControl = generateCurveControl(startLat, startLon, exit.lat, exit.lon, heading);

      // Create plane state
      const startScreenPos = latLonToScreen(startLat, startLon);
      const state = {
        id: planeData.id,
        callsign: planeData.callsign,
        country: planeData.country,
        heading: heading,
        color: planeData.color,

        // Trajectory
        startLat,
        startLon,
        endLat: exit.lat,
        endLon: exit.lon,
        curveControl, // null for straight, {lat, lon} for curved

        // Timing
        startTime: performance.now(),
        duration: durationMs,

        // Current position (will be interpolated)
        lat: startLat,
        lon: startLon,
        screenPos: startScreenPos,
        startScreenPos: startScreenPos,
        progress: 0,

        // Trail history for curved paths
        trailPoints: [{ x: startScreenPos.x, y: startScreenPos.y }],
        lastTrailProgress: 0,
      };

      planes.set(planeData.id, state);
      console.log(`[NEW] ${planeData.callsign || planeData.id.slice(-6)} heading ${heading}° - journey ${(durationMs/1000).toFixed(0)}s`);
    }

  } catch (e) {
    console.error('Fetch error:', e);
    if (isConnected) {
      showOverlay('Reconnecting...');
      isConnected = false;
    }
  }
}

// ─── Initialize Canvas Size ───────────────────────
function resizeCanvas() {
  trailsCanvas.width = window.innerWidth;
  trailsCanvas.height = window.innerHeight;
}

// ─── Main Entry Point ─────────────────────────────
async function main() {
  showOverlay('Connecting...');
  resizeCanvas();

  await loadConfig();

  // Start animation loop
  requestAnimationFrame(animate);

  // Initial fetch
  await fetchFlightData();

  // Poll for updates (to detect new planes)
  setInterval(fetchFlightData, config.pollIntervalMs);
}

// ─── Handle Window Resize ─────────────────────────
window.addEventListener('resize', () => {
  resizeCanvas();
});

// ─── Start ────────────────────────────────────────
main();
