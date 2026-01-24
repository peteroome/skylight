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
