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
